#!/usr/bin/env python3
"""Fetch a complete timed-media transcript with a fast, observable fallback chain."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any
from urllib.parse import parse_qs, urlparse


VERSION = "lite-visual-transcript/4"
SCHEMA = "lite-visual-transcript/v2"
WORD_RE = re.compile(r"[\w\u0600-\u06ff]+", re.UNICODE)


class CaptionsAbsent(RuntimeError):
    """YouTube returned a complete caption inventory with no tracks."""


class CaptionTrackUnusable(RuntimeError):
    """YouTube exposed a caption track, but that track could not be read."""


def video_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname in {"youtu.be", "www.youtu.be"}:
        return parsed.path.strip("/")
    candidate = parse_qs(parsed.query).get("v", [""])[0]
    if candidate:
        return candidate
    match = re.search(r"/(?:shorts|embed)/([^/?#]+)", parsed.path)
    return match.group(1) if match else url


def is_youtube_source(source: str) -> bool:
    host = (urlparse(source).hostname or "").lower()
    return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be"}


def clean_caption(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", html.unescape(value))
    value = re.sub(r"\[(?:Music|Applause|Laughter|موسيقى|تصفيق|ضحك)\]", "", value, flags=re.I)
    return re.sub(r"\s+", " ", value).strip()


def timestamp(seconds: float) -> str:
    whole = max(0, int(seconds))
    return f"[{whole // 3600:02d}:{whole % 3600 // 60:02d}:{whole % 60:02d}]"


def render_entries(entries: list[tuple[float, str]], timestamps: bool) -> str:
    lines: list[str] = []
    previous = ""
    for start, value in entries:
        text = clean_caption(value)
        if not text or text == previous:
            continue
        previous = text
        lines.append(f"{timestamp(start)} {text}" if timestamps else text)
    return "\n".join(lines).strip() + "\n"


def parse_vtt(raw: str, timestamps: bool) -> str:
    entries: list[tuple[float, str]] = []
    blocks = re.split(r"\n\s*\n", raw.replace("\r\n", "\n"))
    for block in blocks:
        lines = [line for line in block.splitlines() if line.strip()]
        time_index = next((index for index, line in enumerate(lines) if "-->" in line), None)
        if time_index is None:
            continue
        match = re.match(r"(?:(\d+):)?(\d+):(\d+)[.,](\d+)", lines[time_index].strip())
        if not match:
            continue
        hours, minutes, seconds, milliseconds = match.groups()
        start = int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) / (10 ** len(milliseconds))
        visible = [clean_caption(line) for line in lines[time_index + 1:] if not line.startswith("NOTE")]
        visible = [line for line in visible if line]
        if visible:
            entries.append((start, visible[-1]))
    return render_entries(entries, timestamps)


def fetch_with_transcript_api(url: str, languages: list[str], timestamps: bool) -> tuple[str, str, dict[str, Any]]:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import TranscriptsDisabled

    api = YouTubeTranscriptApi()
    try:
        tracks = list(api.list(video_id(url)))
    except TranscriptsDisabled as exc:
        raise CaptionsAbsent("youtube-transcript-api reports captions disabled") from exc
    selected = None
    # Prefer human captions across requested languages before generated tracks.
    for generated in (False, True):
        selected = next((track for language in languages for track in tracks if track.language_code == language and track.is_generated is generated), None)
        if selected:
            break
    if selected is None:
        selected = next((track for track in tracks if not track.is_generated), tracks[0] if tracks else None)
    if selected is None:
        raise CaptionsAbsent("youtube-transcript-api returned zero caption tracks")
    try:
        result = selected.fetch()
    except Exception as exc:
        raise CaptionTrackUnusable(f"youtube-transcript-api exposed {selected.language_code} captions but could not fetch them: {exc}") from exc
    entries = [(float(getattr(item, "start", 0)), str(getattr(item, "text", ""))) for item in result]
    return render_entries(entries, timestamps), selected.language_code, {"method": "youtube-transcript-api", "caption_kind": "generated" if selected.is_generated else "manual", "video_id": video_id(url)}


def fetch_with_ytdlp(url: str, languages: list[str], timestamps: bool) -> tuple[str, str, dict[str, Any]]:
    import yt_dlp

    options = {"skip_download": True, "writesubtitles": True, "writeautomaticsub": True, "subtitleslangs": languages, "subtitlesformat": "json3/vtt/best", "quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(options) as client:
        info = client.extract_info(url, download=False)
        manual = info.get("subtitles") or {}
        automatic = info.get("automatic_captions") or {}
        selected = next((language for language in languages if manual.get(language)), None)
        caption_kind = "manual"
        if not selected:
            selected = next((language for language in languages if automatic.get(language)), None)
            caption_kind = "generated"
        if not selected:
            if manual:
                selected, caption_kind = next(iter(manual)), "manual"
            elif automatic:
                selected, caption_kind = next(iter(automatic)), "generated"
        if not selected:
            raise CaptionsAbsent("yt-dlp returned zero manual or generated caption tracks")
        tracks = manual.get(selected) or automatic.get(selected) or []
        track = next((item for item in tracks if item.get("ext") == "json3"), tracks[0] if tracks else None)
        if not track or not track.get("url"):
            raise CaptionTrackUnusable(f"yt-dlp exposed {selected} captions without a downloadable representation")
        try:
            with client.urlopen(track["url"]) as response:
                raw = response.read().decode("utf-8")
            if track.get("ext") == "json3":
                events = json.loads(raw).get("events", [])
                entries = [(float(event.get("tStartMs", 0)) / 1000, "".join(segment.get("utf8", "") for segment in event.get("segs", []))) for event in events]
                transcript = render_entries(entries, timestamps)
            else:
                transcript = parse_vtt(raw, timestamps)
        except Exception as exc:
            raise CaptionTrackUnusable(f"yt-dlp exposed {selected} captions but could not read them: {exc}") from exc
    return transcript, selected, {"method": "yt-dlp-subtitles", "caption_kind": caption_kind, "video_id": str(info.get("id") or video_id(url)), "duration_seconds": info.get("duration")}


def validate_asr_segments(segments: list[dict[str, Any]], duration: float, language: str) -> dict[str, Any]:
    """Fail closed on real ASR boundaries; never synthesize or stretch times."""
    import math
    text = "\n".join(s["text"] for s in segments)
    words = WORD_RE.findall(text)
    previous_end = 0.0
    valid = bool(segments) and math.isfinite(duration) and duration > 0
    max_gap = 0.0
    for segment in segments:
        start, end = float(segment["start"]), float(segment["end"])
        valid = valid and math.isfinite(start) and math.isfinite(end) and start >= previous_end - 1e-9 and end > start and end <= duration + 0.1
        max_gap = max(max_gap, start - previous_end)
        previous_end = end
    letters = [c for c in text if c.isalpha()]
    arabic_ratio = sum('\u0600' <= c <= '\u06ff' for c in letters) / max(1, len(letters))
    import itertools
    longest_repeat = max((sum(1 for _ in group) for _, group in itertools.groupby(segments, key=lambda s: s['text'].strip())), default=0)
    checks = {
        "no_repetition_loop": longest_repeat < 4,
        "monotonic_nonoverlapping_segments": bool(valid),
        "start_near_zero": bool(segments) and segments[0]["start"] <= 5,
        "end_within_five_seconds": bool(segments) and 0 <= duration - segments[-1]["end"] <= 5,
        "no_gap_over_30_seconds": max_gap <= 30,
        "expected_language": arabic_ratio >= 0.7 if language.startswith('ar') else bool(letters),
        "plausible_word_count": 30 <= len(words) / (duration / 60) <= 250 if duration > 0 else False,
        "no_summary_markers": not bool(re.search(r'(?i)(?:here is (?:the|a) (?:summary|transcript)|as an ai|إليك ملخص|بصفتي نموذجا)', text)),
    }
    evidence = {"checks": checks, "passed": all(checks.values()), "maximum_gap_seconds": max_gap, "arabic_letter_ratio": arabic_ratio, "word_count": len(words)}
    if not evidence["passed"]:
        raise RuntimeError("ASR temporal/language gate failed: " + json.dumps(evidence, ensure_ascii=False))
    return evidence


def fetch_with_whisper(source: str, timestamps: bool) -> tuple[str, str, dict[str, Any]]:
    from faster_whisper import WhisperModel

    with tempfile.TemporaryDirectory(prefix="lite-visual-transcript-") as directory:
        path = Path(source)
        if path.is_file():
            audio = path
        else:
            import yt_dlp
            output = str(Path(directory) / "source.%(ext)s")
            with yt_dlp.YoutubeDL({"format": "bestaudio/best", "outtmpl": output, "quiet": True, "no_warnings": True}) as client:
                client.extract_info(source, download=True)
            audio = next(Path(directory).glob("source.*"), None)
            if not audio:
                raise RuntimeError("yt-dlp did not produce fallback audio")
        import subprocess
        audio_hash = hashlib.sha256(audio.read_bytes()).hexdigest()
        duration = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(audio)], text=True).strip())
        model_name = os.environ.get("WHISPER_MODEL", "small")
        started = time.perf_counter()
        replay_path = os.environ.get('WHISPER_REPLAY_EVIDENCE')
        model = None if replay_path else WhisperModel(model_name, compute_type="int8", cpu_threads=int(os.environ.get('WHISPER_CPU_THREADS', '4')))
        retained = []
        correction = None
        correction_start = os.environ.get('WHISPER_CORRECTION_START')
        options = {}
        if correction_start:
            prefix_path = Path(os.environ['WHISPER_PREFIX_EVIDENCE'])
            boundary = float(correction_start)
            raw_prefix = prefix_path.read_bytes()
            rows = [json.loads(line) for line in raw_prefix.decode('utf-8').splitlines() if line.strip()]
            if not rows or any(row.get('audio_sha256') != audio_hash or row.get('model') != model_name for row in rows):
                raise RuntimeError('correction prefix audio/model binding mismatch')
            retained = [{k: row[k] for k in ('start', 'end', 'text')} for row in rows if row['end'] <= boundary]
            if not retained or retained[-1]['end'] != boundary:
                raise RuntimeError('correction must start at an exact retained segment end')
            options['clip_timestamps'] = str(boundary)
            correction = {'start_seconds': boundary, 'prefix_evidence_sha256': hashlib.sha256(raw_prefix).hexdigest(), 'retained_segment_count': len(retained)}
        if replay_path:
            from types import SimpleNamespace
            replay_raw = Path(replay_path).read_bytes()
            replay_rows = [json.loads(line) for line in replay_raw.decode('utf-8').splitlines() if line.strip()]
            if not replay_rows or any(row.get('audio_sha256') != audio_hash or row.get('model') != model_name for row in replay_rows):
                raise RuntimeError('ASR replay audio/model binding mismatch')
            segments = [SimpleNamespace(**{k: row[k] for k in ('start', 'end', 'text')}) for row in replay_rows]
            info = SimpleNamespace(language=os.environ.get('WHISPER_LANGUAGE') or 'unknown')
            correction = {**(correction or {}), 'revalidated_evidence_sha256': hashlib.sha256(replay_raw).hexdigest(), 'asr_rerun': False}
        else:
            segments, info = model.transcribe(str(audio), vad_filter=not bool(correction_start), beam_size=5, temperature=0, condition_on_previous_text=False, language=os.environ.get('WHISPER_LANGUAGE') or None, **options)
        evidence_path = None if replay_path else os.environ.get('WHISPER_EVIDENCE_PATH')
        for segment in segments:
            item = {"start": float(segment.start), "end": float(segment.end), "text": segment.text.strip()}
            if item['text']:
                retained.append(item)
                if evidence_path:
                    with open(evidence_path, 'a', encoding='utf-8') as stream:
                        stream.write(json.dumps({"audio_sha256": audio_hash, "model": model_name, **item}, ensure_ascii=False) + '\n')
        selected = str(info.language or 'unknown')
        quality = validate_asr_segments(retained, duration, selected)
        # Preserve spoken repetitions rather than applying caption de-duplication.
        transcript = '\n'.join((timestamp(s['start']) + ' ' if timestamps else '') + s['text'] for s in retained) + '\n'
        canonical = '\n'.join(s['text'] for s in retained) + '\n'
        return transcript, selected, {"method": "faster-whisper", "caption_kind": "speech-to-text", "model": model_name, "duration_seconds": duration, "source_audio_sha256": audio_hash, "segments": retained, "quality": quality, "canonical_fulltext_sha256": hashlib.sha256(canonical.encode()).hexdigest(), "transcript_sha256": hashlib.sha256(transcript.encode()).hexdigest(), "prompt_version": "verbatim-native-asr/v2-no-prior-text", "condition_on_previous_text": False, "correction": correction, "temperature": 0, "elapsed_ms": round((time.perf_counter()-started)*1000, 2), "token_usage": None, "cache_status": "diagnostic-revalidation" if replay_path else "miss"}


def validate_transcript(transcript: str) -> dict[str, Any]:
    words = WORD_RE.findall(transcript)
    lines = [re.sub(r"^\[\d{2}:\d{2}:\d{2}\]\s*", "", line).strip().lower() for line in transcript.splitlines() if line.strip()]
    duplicate_ratio = (len(lines) - len(set(lines))) / max(1, len(lines))
    checks = {"minimum_words": len(words) >= 20, "plain_text": "WEBVTT" not in transcript and "-->" not in transcript, "duplicate_line_ratio": round(duplicate_ratio, 4)}
    if not checks["minimum_words"] or not checks["plain_text"] or duplicate_ratio > 0.35:
        raise RuntimeError(f"transcript completeness gate failed: {json.dumps(checks)}")
    return checks


def acquire_transcript(source: str, languages: list[str], timestamps: bool, no_audio_fallback: bool) -> tuple[str, str, dict[str, Any], dict[str, Any], list[str]]:
    failures: list[str] = []
    if not is_youtube_source(source):
        transcript, selected, adapter = fetch_with_whisper(source, timestamps)
        return transcript, selected, adapter, validate_transcript(transcript), failures

    caption_absence: list[str] = []
    caption_present_but_unusable: list[str] = []
    for fetcher in (fetch_with_transcript_api, fetch_with_ytdlp):
        try:
            transcript, selected, adapter = fetcher(source, languages=languages, timestamps=timestamps)
            try:
                checks = validate_transcript(transcript)
            except Exception as exc:
                detail = f"{fetcher.__name__}: caption track exists but failed validation: {exc}"
                failures.append(detail)
                caption_present_but_unusable.append(detail)
                continue
            return transcript, selected, adapter, checks, failures
        except CaptionsAbsent as exc:
            detail = f"{fetcher.__name__}: {exc}"
            failures.append(detail)
            caption_absence.append(detail)
        except CaptionTrackUnusable as exc:
            detail = f"{fetcher.__name__}: {exc}"
            failures.append(detail)
            caption_present_but_unusable.append(detail)
        except Exception as exc:
            failures.append(f"{fetcher.__name__}: caption lookup failed: {exc}")

    if caption_present_but_unusable:
        raise RuntimeError("YouTube captions exist but are unreadable or incomplete; audio transcription is forbidden: " + " | ".join(caption_present_but_unusable))
    if not caption_absence:
        raise RuntimeError("YouTube caption availability could not be confirmed; audio transcription is forbidden: " + " | ".join(failures))
    if no_audio_fallback:
        raise RuntimeError("YouTube captions are confirmed absent and audio fallback is disabled: " + " | ".join(caption_absence))

    try:
        transcript, selected, adapter = fetch_with_whisper(source, timestamps)
    except Exception as exc:
        failures.append(f"fetch_with_whisper: {exc}")
        raise RuntimeError("YouTube captions are confirmed absent and audio transcription failed: " + " | ".join(failures)) from exc
    adapter["audio_fallback_reason"] = "youtube_captions_confirmed_absent"
    adapter["caption_absence_evidence"] = caption_absence
    return transcript, selected, adapter, validate_transcript(transcript), failures


def write_manifest(path: str | None, value: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?")
    parser.add_argument("--url", dest="source_option")
    parser.add_argument("--output")
    parser.add_argument("--manifest")
    parser.add_argument("--language", "--languages", default="ar,ar-SA,ar-EG,en")
    parser.add_argument("--timestamps", action="store_true")
    parser.add_argument("--no-audio-fallback", action="store_true")
    args = parser.parse_args(argv)
    source = args.source_option or args.source
    if not source:
        parser.error("one URL or local media path is required")

    started = time.perf_counter()
    languages = [item.strip() for item in args.language.split(",") if item.strip()]
    try:
        transcript, selected, adapter, checks, failures = acquire_transcript(source, languages, args.timestamps, args.no_audio_fallback)
        encoded = transcript.encode("utf-8")
        receipt = {"schema_version": SCHEMA, "extractor_version": VERSION, "status": "complete", "source": source, "language": selected, "method": adapter.get("method"), "caption_kind": adapter.get("caption_kind"), "content_sha256": hashlib.sha256(encoded).hexdigest(), "word_count": len(WORD_RE.findall(transcript)), "character_count": len(transcript), "timestamps": args.timestamps, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2), "checks": checks, "adapter": adapter, "warnings": failures}
        if adapter.get("audio_fallback_reason"):
            receipt["audio_fallback_reason"] = adapter["audio_fallback_reason"]
            receipt["caption_absence_evidence"] = adapter.get("caption_absence_evidence") or []
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(encoded)
            receipt["output"] = str(output)
        write_manifest(args.manifest, receipt)
        if args.output:
            print(json.dumps(receipt, ensure_ascii=False))
        else:
            sys.stdout.write(transcript)
        return 0
    except Exception as exc:
        failures = locals().get("failures", [])
        receipt = {"schema_version": SCHEMA, "extractor_version": VERSION, "status": "blocked", "source": source, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2), "error": str(exc), "failures": failures}
        write_manifest(args.manifest, receipt)
        print(json.dumps(receipt, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
