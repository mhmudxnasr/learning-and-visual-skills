#!/usr/bin/env python3
"""Resolve a YouTube video lacking captions to a verified verbatim Arabic transcript via Gemini.

Caption-first: full caption inventory (youtube-transcript-api + yt-dlp) is checked
exactly as fetch_transcript.py does. Only when a complete inventory positively
reports zero manual and zero generated tracks does this script download the audio
and transcribe it with the Gemini model chain (identical prompt and quality gate to
the production arabic-audio-transcriber worker). It then emits a transcript.text
plus a manifest receipt in the lite-visual-source-extraction schema so the normal
Visual Lite companion pipeline consumes it unchanged.

Quality is gate-failed closed; a "successful" HTTP/model response is not acceptance.
A failed attempt is never displayed as complete.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
FETCH_SCRIPT = SCRIPT_DIR / "fetch_transcript.py"

VERSION = "lite-visual-gemini-youtube-transcript/1"
SCHEMA = "lite-visual-transcript/v2"

DEFAULT_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
]
DEFAULT_PROMPT_VERSION = "arabic-verbatim-v3"
DEV_VARS = Path("/home/mahmud/arabic-audio-transcriber/.dev.vars")

# Same failure markers the production worker uses, so model commentary is rejected.
FORBIDDEN_MARKERS = re.compile(
    r"ملخص التسجيل|إليك التفريغ|here is the transcript|###", re.I
)
WORD_RE = re.compile(r"[\w\u0600-\u06ff]+", re.UNICODE)


def load_api_key(explicit: str | None) -> str | None:
    if explicit:
        return explicit.strip()
    env = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if env:
        return env.strip()
    if DEV_VARS.is_file():
        for line in DEV_VARS.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "GEMINI_API_KEY":
                return value.strip().strip('"\'')
    return None


def format_time(total_seconds: float) -> str:
    whole = max(0, int(total_seconds))
    hours, rem = divmod(whole, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def media_duration(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
         "default=noprint_wrappers=1:nokey=1", str(path)],
        text=True, timeout=120,
    )
    value = float(out.strip())
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError("could not determine audio duration")
    return value


def find_ffmpeg() -> str | None:
    import shutil
    found = shutil.which("ffmpeg") or shutil.which("ffprobe")
    if found and Path(found).name == "ffmpeg":
        return found
    candidate = Path("/home/mahmud/.hermes/tools/ffmpeg-9.0.1-linux-x64/bin/ffmpeg")
    if candidate.is_file():
        return str(candidate)
    return None


def download_audio(url: str, directory: Path) -> tuple[Path, dict[str, Any]]:
    """Fetch audio, preferring a direct audio stream. Returns (path, download_notes).

    YouTube throttles direct media downloads on some clients (HTTP 403 on
    googlevideo) even when metadata and caption listing work. When the default
    audio download fails, fall back to the android-client 360p progressive MP4
    and downsample its audio track to a compact speech-grade MP3 for the model.
    The receipt binds the SHA-256 of the exact bytes sent to the model.
    """
    import yt_dlp
    output = str(directory / "source.%(ext)s")
    try:
        with yt_dlp.YoutubeDL({
            "format": "bestaudio/best",
            "outtmpl": output,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }) as client:
            client.extract_info(url, download=True)
        candidates = sorted(directory.glob("source.*"))
        if candidates:
            return candidates[0], {"download_client": "default", "download_fallback": False}
    except Exception as exc:  # noqa: BLE001
        first_error = str(exc)[:300]
    else:
        first_error = "no file produced"
    try:
        with yt_dlp.YoutubeDL({
            "format": "18/best",
            "outtmpl": str(directory / "fallback.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "extractor_args": {"youtube": {"player_client": ["android"]}},
        }) as client:
            client.extract_info(url, download=True)
        video = next(iter(sorted(directory.glob("fallback.*"), key=lambda p: p.stat().st_size, reverse=True)), None)
        if not video:
            raise RuntimeError("android-client download produced no file")
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("android fallback needs ffmpeg for audio downsampling")
        compact = directory / "compact.mp3"
        done = subprocess.run(
            [ffmpeg, "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", "-y", str(compact)],
            text=True, capture_output=True, timeout=600,
        )
        if done.returncode != 0 or not compact.is_file():
            raise RuntimeError(f"audio downsampling failed: {(done.stderr or '').strip()[:300]}")
        try:
            video.unlink()
        except OSError:
            pass
        return compact, {"download_client": "android-fallback", "download_fallback": True,
                         "default_download_error": first_error,
                         "downsample": "mono-16kHz-48k-mp3"}
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"audio download failed (default: {first_error}; fallback: {exc})") from exc


def transcription_prompt(speaker: str | None, series: str | None,
                         terms: str | None, instructions: str | None) -> str:
    return (
        "فرّغ هذا التسجيل العربي كاملًا تفريغًا حرفيًا أمينًا من أول كلمة إلى آخر كلمة.\n\n"
        "اكتب كل مقطع في سطر مستقل بهذا الشكل فقط:\n[HH:MM:SS] النص المنطوق\n\n"
        "الشروط:\n"
        "- لا تلخص ولا تعِد الصياغة ولا تحذف التكرار المنطوق.\n"
        "- ضع طابعًا زمنيًا حقيقيًا عند بداية كل مقطع دلالي، وبفاصل لا يتجاوز 45 ثانية.\n"
        "- حافظ على الآيات والأحاديث وأسماء العلماء والكتب والمصطلحات العربية.\n"
        "- إذا تعذر سماع كلمة فاكتب [غير واضح] بدل التخمين.\n"
        "- لا تضف عنوانًا أو شرحًا أو Markdown أو خاتمة من عندك.\n"
        "- واصل التفريغ حتى نهاية التسجيل، ولا تتوقف مبكرًا.\n"
        + (f"المتحدث المعروف: {speaker}\n" if speaker else "")
        + (f"السلسلة المعروفة: {series}\n" if series else "")
        + (f"الأسماء والمصطلحات المتوقعة: {terms}\n" if terms else "")
        + (f"تعليمات إضافية: {instructions}\n" if instructions else "")
    ).strip()


def call_gemini(api_key: str, model: str, audio_b64: str, mime_type: str,
                prompt: str, timeout: int = 120) -> tuple[str, dict[str, Any]]:
    import httpx
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [
            {"inlineData": {"mimeType": mime_type, "data": audio_b64}},
            {"text": prompt},
        ]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 8192},
    }
    try:
        response = httpx.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"gemini transport error: {exc}") from exc
    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError(f"gemini non-JSON response ({response.status_code})") from exc
    if response.status_code != 200:
        detail = body.get("error", {}) if isinstance(body, dict) else {}
        code = detail.get("code") or response.status_code
        reason = (detail.get("message") or "").strip()
        if response.status_code == 429 or code == 429:
            raise QuotaExceeded(reason or "gemini quota exceeded")
        raise RuntimeError(f"gemini error {code}: {reason or 'unknown'}")
    parts = ((body.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    text = "".join(str(part.get("text") or "") for part in parts).strip()
    if not text:
        raise RuntimeError("gemini returned empty text")
    usage = body.get("usageMetadata") or {}
    return text, usage


class QuotaExceeded(RuntimeError):
    pass


def parse_timestamped(text: str, duration: float) -> list[dict[str, Any]]:  # noqa: FBT001
    """Port of the worker's parse logic: JSON segments or bracketed/ranged timestamps."""
    clean = re.sub(r"^```(?:json|javascript|text)?\s*", "", text).strip()
    clean = re.sub(r"```\s*$", "", clean).strip()

    def parse_ts(value: str) -> float:
        parts = value.split(":")
        try:
            numbers = [float(p) for p in parts]
            if len(numbers) == 3:
                return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
            if len(numbers) == 2:
                return numbers[0] * 60 + numbers[1]
        except ValueError:
            return -1.0
        return -1.0

    try:
        parsed = json.loads(clean)
        source = parsed if isinstance(parsed, list) else parsed.get("segments") if isinstance(parsed, dict) else None
        if isinstance(source, list) and source:
            segs = []
            for item in source:
                item = item if isinstance(item, dict) else {}
                start = item.get("start_seconds", item.get("startSeconds", parse_ts(str(item.get("startTime") or ""))))
                end = item.get("end_seconds", item.get("endSeconds", parse_ts(str(item.get("endTime") or ""))))
                segs.append({"start_seconds": start, "end_seconds": end, "text": str(item.get("text") or "").strip()})
            if any(isinstance(s["start_seconds"], (int, float)) and s["text"] for s in segs):
                for idx, seg in enumerate(segs):
                    if seg["end_seconds"] <= seg["start_seconds"]:
                        seg["end_seconds"] = source[idx + 1].get("start_seconds", source[idx + 1].get("startSeconds", duration)) if (idx + 1) < len(source) else duration
                return [s for s in segs if isinstance(s["start_seconds"], (int, float)) and s["text"]]
    except (ValueError, TypeError, AttributeError):
        pass

    parsed: list[tuple[str, str]] = []
    for raw_line in re.sub(r"```(?:text)?", "", clean).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        bracketed = re.match(r"^\*{0,2}\[(\d{1,2}:\d{2}(?::\d{2})?)(?:\s*(?:-|–|—|-->|إلى)\s*\d{1,2}:\d{2}(?::\d{2})?)?\]\*{0,2}\s*[:|\-–—]?\s*(.+)$", line)
        ranged = re.match(r"^\*{0,2}(\d{1,2}:\d{2}(?::\d{2})?)\*{0,2}\s*(?:-|–|—|-->|إلى)\s*\d{1,2}:\d{2}(?::\d{2})?\s*[:|]\s*(.+)$", line)
        simple = re.match(r"^\*{0,2}(\d{1,2}:\d{2}(?::\d{2})?)\*{0,2}\s*[:|]\s*(.+)$", line)
        match = bracketed or ranged or simple
        if match:
            parsed.append((match.group(1), match.group(2).strip()))
        elif parsed:
            parsed[-1] = (parsed[-1][0], parsed[-1][1] + " " + line)

    if not parsed:
        return []

    standard = [parse_ts(stamp) for stamp, _ in parsed]
    fractional = []
    for stamp, _ in parsed:
        parts = stamp.split(":")
        try:
            numbers = [float(p) for p in parts]
            if len(numbers) == 3:
                fractional.append(numbers[0] * 60 + numbers[1] + numbers[2] / 100)
            else:
                fractional.append(parse_ts(stamp))
        except ValueError:
            fractional.append(parse_ts(stamp))
    starts = fractional if timestamp_score(fractional, duration) < timestamp_score(standard, duration) else standard
    segments = []
    for (_, text_value), start in zip(parsed, starts):
        start = float(start)
        if start < 0 or not text_value:
            continue
        segments.append({
            "start_seconds": round(start, 3),
            "text": text_value,
        })
    for idx, seg in enumerate(segments):
        seg["end_seconds"] = round(max(seg["start_seconds"] + 0.5, segments[idx + 1]["start_seconds"] if idx + 1 < len(segments) else duration), 3)
    return segments


def timestamp_score(values: list[float], duration: float) -> float:
    if not values or any(not math.isfinite(v) or v < 0 for v in values):
        return float("inf")
    penalty = 0.0
    for index in range(1, len(values)):
        if values[index] <= values[index - 1]:
            penalty += 10_000
        if values[index] - values[index - 1] > 90:
            penalty += 2_000
    last = values[-1]
    if last > duration + 60:
        penalty += 100_000 + last
    return penalty + abs(duration - last)


def validate_quality(segments: list[dict[str, Any]], duration: float) -> tuple[bool, dict[str, Any]]:
    warnings: list[str] = []
    failures: list[str] = []
    if not segments:
        return False, {"passed": False, "failure_reasons": ["لم يُنتج النموذج مقاطع ذات طوابع زمنية حقيقية."]}

    monotonic = True
    max_interval = 0.0
    for index, segment in enumerate(segments):
        if segment["start_seconds"] < 0 or segment["end_seconds"] <= segment["start_seconds"]:
            monotonic = False
        if index:
            previous = segments[index - 1]
            if segment["start_seconds"] <= previous["start_seconds"]:
                monotonic = False
            max_interval = max(max_interval, segment["start_seconds"] - previous["start_seconds"])
    if not monotonic:
        failures.append("الطوابع الزمنية غير متسلسلة.")
    first = segments[0]["start_seconds"]
    last_start = segments[-1]["start_seconds"]
    if first > 5:
        failures.append(f"بداية التفريغ متأخرة عند {first} ثانية.")
    if max_interval > 60:
        failures.append(f"فاصل الطوابع الزمنية كبير جدًا ({round(max_interval)} ثانية).")
    elif max_interval > 45:
        warnings.append(f"أطول فاصل زمني {round(max_interval)} ثانية.")

    full_text = " ".join(s["text"] for s in segments)
    words = full_text.split()
    minutes = max(duration / 60, 1 / 60)
    words_per_minute = round(len(words) / minutes, 1)
    arabic = sum(1 for c in full_text if "\u0600" <= c <= "\u06ff")
    latin = sum(1 for c in full_text if c.isascii() and c.isalpha())
    arabic_ratio = round(arabic / max(1, arabic + latin), 3)
    if arabic_ratio < 0.85:
        failures.append(f"نسبة النص العربي منخفضة ({round(arabic_ratio * 100)}%).")
    minimum_wpm = 55 if duration >= 120 else 35
    if words_per_minute < minimum_wpm:
        failures.append(f"النص قصير مقارنة بمدة التسجيل ({words_per_minute} كلمة/دقيقة).")
    last_span = duration - last_start
    last_words = len(segments[-1]["text"].split())
    last_density = last_words / max(last_span / 60, 0.1)
    if last_start < duration - 90 or (last_span > 45 and last_density < 35):
        failures.append("نهاية التفريغ لا تغطي الجزء الأخير من التسجيل بصورة موثوقة.")
    if FORBIDDEN_MARKERS.search(full_text):
        failures.append("أضاف النموذج شرحًا أو ملخصًا غير منطوق.")

    duration_covered = not any("نهاية" in r or "قصير" in r for r in failures)
    passed = not failures
    return passed, {
        "passed": passed,
        "timestamps_monotonic": monotonic,
        "duration_covered": duration_covered,
        "first_timestamp_seconds": first,
        "last_timestamp_seconds": segments[-1]["end_seconds"],
        "maximum_gap_seconds": round(max_interval, 3),
        "arabic_ratio": arabic_ratio,
        "word_count": len(words),
        "words_per_minute": words_per_minute,
        "warnings": warnings,
        "failure_reasons": failures,
    }


def is_youtube(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be"}


def caption_absent_evidence(url: str, languages: list[str], timestamps: bool) -> tuple[str | None, list[str]]:
    """Run fetch_transcript.py in caption-only mode, retrying transients.
    Returns (caption-transcript-or-None, absence_evidence)."""
    evidence: list[str] = []
    last_receipt: dict[str, Any] = {}
    attempts = 3
    for retry in range(attempts):
        with tempfile.TemporaryDirectory(prefix="gemini-caption-check-") as directory:
            out = Path(directory) / "src.txt"
            manifest = Path(directory) / "receipt.json"
            cmd = ["python3", str(FETCH_SCRIPT), url, "--output", str(out), "--manifest", str(manifest),
                   "--languages", ",".join(languages), "--no-audio-fallback"]
            if timestamps:
                cmd.append("--timestamps")
            done = subprocess.run(cmd, text=True, capture_output=True, timeout=600)
            receipt = {}
            if manifest.is_file():
                try:
                    receipt = json.loads(manifest.read_text(encoding="utf-8"))
                except ValueError:
                    pass
            last_receipt = receipt
            status = receipt.get("status")
            if done.returncode == 0 and status == "complete" and out.is_file():
                return out.read_text(encoding="utf-8"), []
            # Complete caption inventory with zero tracks => captions confirmed absent.
            if done.returncode != 0 and status == "blocked":
                err = receipt.get("error") or done.stderr
                if "audio fallback is disabled" in err or "captions are confirmed absent" in err:
                    evidence = [str(detail) for detail in (receipt.get("failures") or [])]
                    evidence.extend(receipt.get("caption_absence_evidence") or [])
                    # fetch_transcript buries the per-adapter findings in the error
                    # string; split them out so the evidence is never empty.
                    tail = err.split(": ", 1)
                    if len(tail) == 2:
                        evidence.extend(part.strip() for part in tail[1].split(" | ") if part.strip())
                    if err not in evidence:
                        evidence.append(err)
                    return None, evidence
            # Transient failure (network/IP throttle): retry before giving up.
            if retry + 1 < attempts:
                time.sleep(2 ** retry)
    raise RuntimeError(
        "caption gate did not positively confirm absence: "
        + (json.dumps(last_receipt, ensure_ascii=False) if last_receipt else "no receipt")
    )


def render_transcript(segments: list[dict[str, Any]], timestamps: bool) -> tuple[str, str]:
    lines = []
    canonical = []
    for segment in segments:
        text = segment["text"].strip()
        if not text:
            continue
        canonical.append(text)
        lines.append((format_time(segment["start_seconds"]) + " " + text) if timestamps else text)
    return "\n".join(lines).strip() + "\n", "\n".join(canonical).strip() + "\n"


def transcribe(url: str, api_key: str, models: list[str], prompt_version: str,
               timestamps: bool, speaker: str | None, series: str | None,
               terms: str | None, instructions: str | None,
               languages: list[str], agent: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="lite-visual-gemini-") as directory:
        work = Path(directory)
        caption_transcript, absence = caption_absent_evidence(url, languages, timestamps)
        if caption_transcript is not None:
            # Caption-first: a complete published track is preferred over audio.
            rebuild = []
            for raw_line in caption_transcript.splitlines():
                if not raw_line.strip():
                    continue
                m = re.match(r"^\[(\d{2}):(\d{2}):(\d{2})\]\s*(.*)$", raw_line)
                if m:
                    secs = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
                    rebuild.append({"start_seconds": float(secs), "end_seconds": float(secs), "text": m.group(4)})
            return {
                "schema_version": SCHEMA,
                "extractor_version": VERSION,
                "status": "complete",
                "source": url,
                "language": "ar",
                "method": "youtube-transcript-api",
                "caption_kind": "captions",
                "content_sha256": hashlib.sha256(caption_transcript.encode("utf-8")).hexdigest(),
                "word_count": len(WORD_RE.findall(caption_transcript)),
                "character_count": len(caption_transcript),
                "timestamps": timestamps,
                "checks": {"quality_passed": True},
                "adapter": {"method": "youtube-transcript-api", "caption_kind": "captions", "kind": "youtube",
                            "segments": rebuild if rebuild else None,
                            "full_text": caption_transcript},
                "warnings": ["Captions were present and used; Gemini audio fallback was not needed."],
            }
        media, download_notes = download_audio(url, work)
        audio_bytes = media.read_bytes()
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        audio_sha = hashlib.sha256(audio_bytes).hexdigest()
        duration = media_duration(media)
        mime = "audio/mp4" if media.suffix in {".m4a", ".mp4"} else "audio/mpeg"
        prompt = transcription_prompt(speaker, series, terms, instructions)

        attempts = []
        selected_model = None
        usage = {}
        last_error = None
        last_quality = {}
        segments = []
        for model in models:
            started = time.perf_counter()
            try:
                text, model_usage = call_gemini(api_key, model, audio_b64, mime, prompt)
                candidate = parse_timestamped(text, duration)
                passed, quality = validate_quality(candidate, duration)
                usage = {k: usage.get(k, 0) + (model_usage.get(k) or 0) for k in ("promptTokenCount", "candidatesTokenCount", "totalTokenCount")}
                attempts.append({"model": model, "status": "passed" if passed else "failed_quality",
                                 "processing_seconds": round(time.perf_counter() - started, 3),
                                 "quality": quality})
                segments = candidate
                last_quality = quality
                if passed:
                    selected_model = model
                    break
            except QuotaExceeded as exc:
                attempts.append({"model": model, "status": "quota_exceeded"})
                last_error = str(exc)
            except RuntimeError as exc:
                attempts.append({"model": model, "status": "provider_error", "error_detail": str(exc)})
                last_error = str(exc)

        if not selected_model:
            raise RuntimeError("all gemini models failed or failed quality: " + json.dumps(attempts, ensure_ascii=False))

        transcript, canonical = render_transcript(segments, timestamps)
        transcript_sha = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
        canonical_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        return {
            "schema_version": SCHEMA,
            "extractor_version": VERSION,
            "status": "complete",
            "source": url,
            "language": "ar",
            "method": "gemini",
            "caption_kind": "speech-to-text",
            "content_sha256": hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
            "word_count": len(WORD_RE.findall(transcript)),
            "character_count": len(transcript),
            "timestamps": timestamps,
            "checks": {"quality_passed": True},
            "adapter": {
                "method": "gemini",
                "kind": "youtube",
                "model": selected_model,
                "model_chain": models,
                "prompt_version": prompt_version,
                "duration_seconds": duration,
                "source_audio_sha256": audio_sha,
                "mime_type": mime,
                "download": download_notes,
                "segments": segments,
                "quality": last_quality,
                "canonical_fulltext_sha256": canonical_sha,
                "transcript_sha256": transcript_sha,
                "temperature": 0,
                "token_usage": usage,
                "model_attempts": attempts,
                "cache_status": "miss",
            },
            "audio_fallback_reason": "youtube_captions_confirmed_absent",
            "caption_absence_evidence": absence,
            "audio_fallback_agent": agent,
            "warnings": list(last_quality.get("warnings") or []),
        }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?")
    parser.add_argument("--url", dest="source_option")
    parser.add_argument("--output", "--output-text", dest="output")
    parser.add_argument("--manifest")
    parser.add_argument("--api-key", help="Gemini API key (overrides .dev.vars / env)")
    parser.add_argument("--model", dest="model", help="primary Gemini model")
    parser.add_argument("--language", "--languages", default="ar,ar-SA,ar-EG,en")
    parser.add_argument("--timestamps", action="store_true")
    parser.add_argument("--no-timestamps", action="store_true")
    parser.add_argument("--speaker")
    parser.add_argument("--series")
    parser.add_argument("--terms")
    parser.add_argument("--instructions")
    parser.add_argument("--agent", default="hermes")
    args = parser.parse_args(argv)

    source = args.source_option or args.source
    if not source:
        parser.error("one YouTube URL is required")
    if not is_youtube(source):
        parser.error("this script only accepts YouTube URLs; use fetch_transcript.py for other sources")
    api_key = load_api_key(args.api_key)
    if not api_key:
        write_json(Path(args.manifest) if args.manifest else Path.cwd() / "gemini-receipt.json",
                   {"schema_version": SCHEMA, "extractor_version": VERSION, "status": "blocked",
                    "source": source, "error": "GEMINI_API_KEY not found in .dev.vars or env"})
        print("blocked: GEMINI_API_KEY not found (set --api-key or add to .dev.vars)", file=sys.stderr)
        return 1

    models = [args.model] if args.model else DEFAULT_MODELS
    if args.model and args.model not in models:
        models.insert(0, args.model)
    models = list(dict.fromkeys(models))
    languages = [item.strip() for item in args.language.split(",") if item.strip()]
    timestamps = not args.no_timestamps if (args.timestamps or args.no_timestamps) else True

    started = time.perf_counter()
    try:
        receipt = transcribe(source, api_key, models, DEFAULT_PROMPT_VERSION, timestamps,
                             args.speaker, args.series, args.terms, args.instructions,
                             languages, args.agent)
        receipt["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        if args.output:
            adapter = receipt.get("adapter") or {}
            full_text = adapter.get("full_text")
            if full_text is not None:
                transcript = full_text if full_text.endswith("\n") else full_text + "\n"
            else:
                segments = adapter.get("segments") or []
                transcript, canonical = render_transcript(segments, timestamps)
            Path(args.output).write_text(transcript, encoding="utf-8")
            receipt["output"] = str(Path(args.output))
        if args.manifest:
            write_json(Path(args.manifest), receipt)
        print(json.dumps(receipt, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        failure = {"schema_version": SCHEMA, "extractor_version": VERSION, "status": "blocked",
                   "source": source, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                   "error": str(exc)}
        if args.manifest:
            write_json(Path(args.manifest), failure)
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())