#!/usr/bin/env python3
"""Convert auto-caption VTT to clean continuous Arabic text.

YouTube auto-caption VTT is a rolling window: each cue has a word-timing
line full of <c> tags plus one clean cumulative line. This script takes the
clean cumulative line per cue, strips tags/music markers, and dedupes the
rollover so the output reads once, in order.
"""
import re, sys

def strip_tags(line):
    line = re.sub(r'<[^>]+>', '', line)
    line = re.sub(r'\s+', ' ', line)
    return line.strip()

def merge_overlap(previous, current):
    """Merge rolling-caption cues without repeating their shared window."""
    if not previous:
        return current
    if current in previous:
        return previous
    if previous in current:
        return current
    left = previous.split()
    right = current.split()
    for size in range(min(len(left), len(right)), 0, -1):
        if left[-size:] == right[:size]:
            return ' '.join(left + right[size:])
    return ' '.join(left + right)

def clean_vtt(path):
    with open(path, encoding='utf-8') as f:
        raw = f.read()
    # Drop the WEBVTT header block before the first cue
    raw = re.sub(r'^(WEBVTT.*?)(?=\d{2}:\d{2}:\d{2}\.\d{3}\s*-->)', '', raw, flags=re.S)
    blocks = re.split(r'\n(?=\d{2}:\d{2}:\d{2}\.\d{3}\s*-->)', raw)
    merged = ''
    for b in blocks:
        lines = b.strip().split('\n')
        cleaned = []
        for ln in lines[1:]:  # lines[0] is the timestamp
            t = strip_tags(ln)
            t = re.sub(r'\[موسيقى\]|\[تصفيق\]|\[Music\]|\[Applause\]', '', t).strip()
            if t:
                cleaned.append(t)
        if not cleaned:
            continue
        full = cleaned[-1]  # clean cumulative line
        next_merged = merge_overlap(merged, full)
        if next_merged == merged:
            continue
        merged = next_merged
    return re.sub(r'\s+', ' ', merged).strip()

if __name__ == '__main__':
    print(clean_vtt(sys.argv[1]))
