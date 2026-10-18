#!/usr/bin/env python3
"""Render a workdir's companion.md into companion.html in the one fixed Compass reading design.

usage: build_companion.py WORKDIR

The author writes only teaching content in the small Markdown dialect described in
references/format.md; layout, typography and colour live here, so every companion looks
the same and nothing is improvised. Only broken format, canned filler phrases and emoji stop
the build; length, box counts and register are the author's judgement, not a gate.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"

BOXES = {"key": "الفكرة الأساسية", "limit": "حدود الكلام ده", "added": "توضيح مضاف", "example": "مثال من المصدر"}
VISUALS = {"compare", "steps", "bars", "stats", "timeline", "terms"}
BLOCKS = set(BOXES) | VISUALS | {"thesis"}
KINDS = {"video": "فيديو", "article": "مقال", "book": "كتاب", "chapter": "فصل", "podcast": "بودكاست", "lecture": "محاضرة", "paper": "ورقة بحثية", "talk": "محاضرة"}

# Filler that the reader has learned to skip; each one is replaced by a sentence that says something.
CANNED = ["في عالمنا المتسارع", "دعنا نغوص", "دعونا نغوص", "خلينا نغوص", "من الجدير بالذكر", "وهنا تكمن الأهمية", "تجدر الإشارة", "في هذا المقال سوف",
    "في هذا الفيديو سوف", "في هذه المقالة", "بص يا سيدي", "يا صديقي", "رحلة ممتعة", "رحلة شيقة", "لا يخفى على أحد", "في نهاية المطاف", "بكل بساطة",
    "سنستعرض", "هنستعرض في السطور الجاية", "في السطور القادمة", "عزيزي القارئ", "اربط الحزام", "خلاصة القول",
    "game changer", "deep dive", "let's dive"]
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐✅❌]")
LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z0-9'’&+/.\-]*(?:,?[ ]+[A-Za-z0-9][A-Za-z0-9'’&+/.\-]*)*")
WORD = re.compile(r"[\w؀-ۿ]+")

class BuildError(Exception):
    pass


def fail(line: int, message: str) -> None:
    raise BuildError(f"companion.md:{line}: {message}")


# ---------- inline text ----------

def inline(text: str) -> str:
    """Escape, then apply code, links, Latin isolation, bold and emphasis. No raw HTML survives."""
    slots: list[str] = []

    def keep(fragment: str) -> str:
        slots.append(fragment)
        return f"\x00{len(slots) - 1}\x00"

    text = re.sub(r"`([^`]+)`", lambda m: keep(f'<code dir="ltr">{html.escape(m.group(1))}</code>'), text)

    def link(m: re.Match[str]) -> str:
        label, url = m.group(1), m.group(2)
        if not re.match(r"https?://", url):
            return m.group(0)
        return keep(f'<a href="{html.escape(url, quote=True)}">{isolate(html.escape(label))}</a>')

    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)
    text = isolate(html.escape(text, quote=False))
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])", r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: slots[int(m.group(1))], text)


def isolate(escaped: str) -> str:
    """Wrap English runs in <bdi> so they never scramble the surrounding RTL sentence."""
    def bdi(core: str) -> str:
        # Short terms stay on one line; long English passages may wrap.
        return f'<bdi class="nw">{core}</bdi>' if len(core) <= 32 else f"<bdi>{core}</bdi>"

    def wrap(m: re.Match[str]) -> str:
        if m.group(1):
            return bdi(m.group(1))
        run = m.group(0)
        tail = re.search(r"[.\-/]+$", run)
        core, rest = (run[: tail.start()], run[tail.start():]) if tail else (run, "")
        return bdi(core) + rest if core else run
    # An English gloss in parentheses is isolated with its parentheses, so they never mirror.
    pattern = re.compile(r"(\(" + LATIN_RUN.pattern + r"\))|" + LATIN_RUN.pattern)
    parts = re.split(r"(&[a-z]+;|&#\d+;|\x00\d+\x00)", escaped)
    return "".join(part if i % 2 else pattern.sub(wrap, part) for i, part in enumerate(parts))


def plain(text: str) -> str:
    return re.sub(r"[*`]|\[([^\]]+)\]\([^)]+\)", lambda m: m.group(1) or "", text)


# ---------- block parsing ----------

def front_matter(lines: list[str]) -> tuple[dict[str, str], int]:
    if not lines or lines[0].strip() != "---":
        fail(1, "start with a --- front matter block (title, source_title, url)")
    meta: dict[str, str] = {}
    for index in range(1, len(lines)):
        line = lines[index].strip()
        if line == "---":
            for key in ("title", "source_title", "url"):
                if not meta.get(key):
                    fail(1, f"front matter needs `{key}:`")
            if not re.match(r"https?://", meta["url"]):
                fail(1, "front matter `url:` must be the original http(s) link")
            return meta, index + 1
        if line and ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip('"')
    fail(1, "front matter is not closed with ---")
    raise AssertionError


def flow(lines: list[tuple[int, str]]) -> list[dict]:
    """Paragraphs, ### subheads, lists, quotes and tables from a run of lines."""
    out: list[dict] = []
    i = 0
    while i < len(lines):
        number, line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("#"):
            if not stripped.startswith("### "):
                fail(number, "only `## ` (unit) and `### ` (sub-point) headings exist; the title comes from front matter")
            out.append({"type": "h3", "text": stripped[4:].strip(), "line": number})
            i += 1
            continue
        if re.match(r"([-*]|\d+[.)]|[٠-٩]+[.)])\s", stripped):
            ordered = not stripped[0] in "-*"
            items: list[str] = []
            while i < len(lines):
                number, line = lines[i]
                s = line.strip()
                if re.match(r"([-*]|\d+[.)]|[٠-٩]+[.)])\s", s):
                    items.append(re.sub(r"^([-*]|\d+[.)]|[٠-٩]+[.)])\s+", "", s))
                elif s and line.startswith(("  ", "\t")) and items:
                    items[-1] += " " + s
                else:
                    break
                i += 1
            out.append({"type": "ol" if ordered else "ul", "items": items, "line": number})
            continue
        if stripped.startswith(">"):
            quote: list[str] = []
            while i < len(lines) and lines[i][1].strip().startswith(">"):
                quote.append(lines[i][1].strip()[1:].strip())
                i += 1
            cite = ""
            if quote and re.match(r"^(—|--|–)\s*", quote[-1]):
                cite = re.sub(r"^(—|--|–)\s*", "", quote.pop())
            if not paragraphs(quote):
                fail(number, "this quote has an attribution but no quoted words; put the exact words on `> ` lines above `> — who`")
            out.append({"type": "quote", "paras": paragraphs(quote), "cite": cite, "line": number})
            continue
        caption = ""
        if re.match(r"^(جدول|Table)\s*:", stripped) and i + 1 < len(lines) and lines[i + 1][1].strip().startswith("|"):
            caption = stripped.split(":", 1)[1].strip()
            i += 1
            number, line = lines[i]
            stripped = line.strip()
        if stripped.startswith("|"):
            rows: list[list[str]] = []
            while i < len(lines) and lines[i][1].strip().startswith("|"):
                cells = [cell.strip() for cell in lines[i][1].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
                    rows.append(cells)
                i += 1
            if len(rows) < 2:
                fail(number, "a table needs a header row and at least one data row")
            width = len(rows[0])
            if any(len(row) != width for row in rows):
                fail(number, "every table row needs the same number of cells")
            out.append({"type": "table", "caption": caption, "rows": rows, "line": number})
            continue
        para = [stripped]
        i += 1
        while i < len(lines):
            s = lines[i][1].strip()
            if not s or s.startswith(("#", ">", "|", ":::")) or re.match(r"([-*]|\d+[.)])\s", s):
                break
            para.append(s)
            i += 1
        out.append({"type": "p", "text": " ".join(para), "line": number})
    return out


def paragraphs(lines: list[str]) -> list[str]:
    paras, current = [], []
    for line in lines + [""]:
        if line.strip():
            current.append(line.strip())
        elif current:
            paras.append(" ".join(current))
            current = []
    return paras


def parse(text: str) -> tuple[dict[str, str], list[dict], list[dict]]:
    if "<" in re.sub(r"`[^`]*`", "", text) and re.search(r"<\s*/?\s*[a-zA-Z]", re.sub(r"`[^`]*`", "", text)):
        line = next(n for n, l in enumerate(text.splitlines(), 1) if re.search(r"<\s*/?\s*[a-zA-Z]", re.sub(r"`[^`]*`", "", l)))
        fail(line, "no raw HTML: write Markdown and the ::: blocks; the design is fixed by the builder")
    lines = text.splitlines()
    meta, start = front_matter(lines)
    opening: list[dict] = []
    units: list[dict] = []
    target = opening
    run: list[tuple[int, str]] = []

    def flush() -> None:
        target.extend(flow(run))
        run.clear()

    i = start
    while i < len(lines):
        number, line = i + 1, lines[i]
        s = line.strip()
        if s.startswith("## "):
            flush()
            units.append({"title": s[3:].strip(), "line": number, "body": []})
            target = units[-1]["body"]
        elif s.startswith(":::"):
            flush()
            head = s[3:].strip().split()
            if not head:
                fail(number, "a ::: block closes only an open block; open one with :::name")
            name, args = head[0], head[1:]
            if name not in BLOCKS:
                fail(number, f"unknown block :::{name}; use one of {', '.join(sorted(BLOCKS))}")
            body: list[tuple[int, str]] = []
            i += 1
            while i < len(lines) and lines[i].strip() != ":::":
                if lines[i].strip().startswith(":::"):
                    fail(i + 1, f":::{name} opened on line {number} is not closed before another block")
                body.append((i + 1, lines[i]))
                i += 1
            if i >= len(lines):
                fail(number, f":::{name} is never closed with :::")
            if not any(l.strip() for _, l in body):
                fail(number, f":::{name} is empty")
            target.append({"type": "block", "name": name, "args": args, "body": body, "line": number})
        else:
            run.append((number, line))
        i += 1
    flush()
    return meta, opening, units


# ---------- rendering ----------

def render_flow(items: list[dict]) -> str:
    out = []
    for item in items:
        kind = item["type"]
        if kind == "p":
            out.append(f"<p>{inline(item['text'])}</p>")
        elif kind == "h3":
            out.append(f"<h3>{inline(item['text'])}</h3>")
        elif kind in ("ul", "ol"):
            out.append(f"<{kind}>" + "".join(f"<li>{inline(text)}</li>" for text in item["items"]) + f"</{kind}>")
        elif kind == "quote":
            cite = f"<cite>{inline(item['cite'])}</cite>" if item["cite"] else ""
            out.append("<blockquote>" + "".join(f"<p>{inline(p)}</p>" for p in item["paras"]) + cite + "</blockquote>")
        elif kind == "table":
            head, *rows = item["rows"]
            caption = f"<caption>{inline(item['caption'])}</caption>" if item["caption"] else ""
            numeric = [all(re.fullmatch(r"[-+]?[\d٠-٩.,]+\s*%?", row[c]) for row in rows) for c in range(len(head))]
            cls = lambda c: ' class="num"' if numeric[c] else ""
            body = "".join("<tr>" + "".join(
                (f'<th scope="row">{inline(cell)}</th>' if c == 0 and len(head) > 2 else f"<td{cls(c)}>{inline(cell)}</td>")
                for c, cell in enumerate(row)) + "</tr>" for row in rows)
            heads = "".join(f'<th scope="col"{cls(c)}>{inline(cell)}</th>' for c, cell in enumerate(head))
            out.append(f'<div class="table">{"<table>"}{caption}<thead><tr>{heads}</tr></thead><tbody>{body}</tbody></table></div>')
        elif kind == "block":
            out.append(render_block(item))
    return "\n".join(out)


def list_items(body: list[tuple[int, str]], name: str) -> list[tuple[int, str]]:
    items: list[tuple[int, str]] = []
    for number, line in body:
        s = line.strip()
        if not s:
            continue
        if re.match(r"([-*]|\d+[.)]|[٠-٩]+[.)])\s", s):
            items.append((number, re.sub(r"^([-*]|\d+[.)]|[٠-٩]+[.)])\s+", "", s)))
        elif items and line.startswith(("  ", "\t")):
            items[-1] = (items[-1][0], items[-1][1] + " " + s)
        else:
            fail(number, f":::{name} holds only list items (`- ...`)")
    return items


def label_and_detail(text: str) -> tuple[str, str]:
    m = re.match(r"^\*\*(.+?)\*\*\s*[—:–-]?\s*(.*)$", text)
    return (m.group(1), m.group(2)) if m else ("", text)


def render_block(block: dict) -> str:
    name, args, body, line = block["name"], block["args"], block["body"], block["line"]
    if name in BOXES:
        title = "مثال توضيحي مضاف" if name == "example" and "added" in args else BOXES[name]
        return f'<aside class="box box-{name}"><p class="box-label" data-supporting>{title}</p>{render_flow(flow(body))}</aside>'
    if name == "thesis":
        return '<div class="thesis">' + render_flow(flow(body)) + "</div>"
    if name == "compare":
        sides: list[dict] = []
        for number, text in body:
            s = text.strip()
            if s.startswith("### "):
                sides.append({"title": s[4:].strip(), "lines": []})
            elif s and not sides:
                fail(number, ":::compare starts each side with `### side title`")
            elif sides:
                sides[-1]["lines"].append((number, text))
        if not 2 <= len(sides) <= 3:
            fail(line, ":::compare needs two or three `### ` sides answering the same question")
        cells = "".join(f'<section><p class="side" data-supporting>{inline(side["title"])}</p>{render_flow(flow(side["lines"]))}</section>' for side in sides)
        return f'<div class="compare" data-sides="{len(sides)}">{cells}</div>'
    captions = [(n, l) for n, l in body if name == "bars" and l.strip().startswith(("caption:", "عنوان:"))]
    items = list_items([row for row in body if row not in captions], name)
    if name == "steps":
        if len(items) < 2:
            fail(line, ":::steps needs at least two ordered steps")
        proposed = "proposed" in args
        lis = "".join(f"<li>{('<strong>' + inline(l) + '</strong>') if l else ''}<span>{inline(d)}</span></li>" for l, d in (label_and_detail(t) for _, t in items))
        legend = '<p class="legend" data-supporting>ده تسلسل مقترح للتفسير، مش نتيجة أثبتها المصدر.</p>' if proposed else ""
        kind = ' data-kind="proposed"' if proposed else ""
        return f'<ol class="steps"{kind}>{lis}</ol>{legend}'
    if name == "terms":
        rows = []
        for number, text in items:
            term, detail = label_and_detail(text)
            if not term or not detail:
                fail(number, "write each term as `- **المصطلح** (English): المعنى`")
            rows.append(f"<dt>{inline(term)}</dt><dd>{inline(detail)}</dd>")
        return f'<dl class="terms">{"".join(rows)}</dl>'
    if name == "timeline":
        rows = []
        for number, text in items:
            if "|" not in text:
                fail(number, "write each moment as `- when | what happened`")
            when, what = (part.strip() for part in text.split("|", 1))
            rows.append(f'<li><span class="when">{inline(when)}</span>{inline(what)}</li>')
        return f'<ol class="timeline">{"".join(rows)}</ol>'
    if name == "stats":
        if not 2 <= len(items) <= 4:
            fail(line, ":::stats shows two to four of the source's own numbers")
        cells = []
        for number, text in items:
            if "|" not in text:
                fail(number, "write each number as `- 49% | what it measures`")
            value, label = (part.strip() for part in text.split("|", 1))
            cells.append(f'<div><strong dir="ltr">{html.escape(value)}</strong><span>{inline(label)}</span></div>')
        return f'<div class="stats">{"".join(cells)}</div>'
    if name == "bars":
        try:
            scale = float(args[0]) if args else 100.0
        except ValueError:
            fail(line, "write :::bars with its scale maximum, e.g. `:::bars 100 %`")
        unit = args[1] if len(args) > 1 else ""
        caption = captions[0][1].split(":", 1)[1].strip() if captions else ""
        rows = []
        for number, text in items:
            parts = [part.strip() for part in text.split("|")]
            if len(parts) < 2:
                fail(number, "write each bar as `- label | value`")
            try:
                value = float(parts[1].replace(",", ""))
            except ValueError:
                fail(number, f"bar value `{parts[1]}` is not a number")
            if not 0 <= value <= scale:
                fail(number, f"bar value {parts[1]} is outside the 0–{scale:g} scale")
            note = f'<span class="bar-note" data-supporting>{inline(parts[2])}</span>' if len(parts) > 2 and parts[2] else ""
            rows.append(f'<li><span class="bar-label">{inline(parts[0])}{note}</span><span class="track"><i style="--v:{value / scale * 100:.2f}"></i></span><b dir="ltr">{html.escape(parts[1])}{html.escape(unit)}</b></li>')
        if not rows:
            fail(line, ":::bars needs `- label | value` rows")
        figcaption = f"{inline(caption)} — " if caption else ""
        return f'<figure class="bars"><ol>{"".join(rows)}</ol><figcaption>{figcaption}المقياس من 0 لـ {scale:g}{html.escape(unit)}</figcaption></figure>'
    raise AssertionError(name)


# ---------- quality gate ----------

def text_of(items: list[dict]) -> str:
    chunks = []
    for item in items:
        if item["type"] in ("p", "h3"):
            chunks.append(item["text"])
        elif item["type"] in ("ul", "ol"):
            chunks.extend(item["items"])
        elif item["type"] == "quote":
            chunks.extend(item["paras"])
        elif item["type"] == "table":
            chunks.extend(cell for row in item["rows"] for cell in row)
        elif item["type"] == "block":
            chunks.extend(line for _, line in item["body"])
    return plain(" ".join(chunks))


def check(opening: list[dict], units: list[dict]) -> None:
    if not units:
        fail(1, "teach the source in `## ` units, one idea or question each")
    theses = [b for b in opening if b["type"] == "block" and b["name"] == "thesis"]
    if len(theses) != 1:
        fail(1, "put exactly one :::thesis before the first `## ` unit: the source's question and its answer")
    for unit in units:
        for item in unit["body"]:
            if item["type"] == "block" and item["name"] == "thesis":
                fail(item["line"], ":::thesis belongs in the opening, before the first unit")
    everything = text_of(opening) + " " + " ".join(u["title"] + " " + text_of(u["body"]) for u in units)
    lowered = everything.lower()
    for phrase in CANNED:
        if phrase.lower() in lowered:
            fail(1, f"canned phrase «{phrase}»; replace the sentence with one that says something specific")
    if EMOJI.search(everything):
        fail(1, "no emoji")


# ---------- page ----------

def page(meta: dict[str, str], opening: list[dict], units: list[dict]) -> str:
    kind = KINDS.get(meta.get("kind", "").lower(), meta.get("kind", ""))
    kicker = " · ".join(inline(part) for part in (kind, meta.get("creator", "")) if part)
    question = f'<p class="question"><span data-supporting>السؤال اللي بنجاوب عليه</span>{inline(meta["question"])}</p>' if meta.get("question") else ""
    source = f'{inline(meta["source_title"])}' + (f" — {inline(meta['creator'])}" if meta.get("creator") else "")
    sections = "\n".join(f'<section class="unit" id="u{n}">\n<h2>{inline(u["title"])}</h2>\n{render_flow(u["body"])}\n</section>' for n, u in enumerate(units, 1))
    css = (ASSETS / "fonts.css").read_text(encoding="utf-8") + (ASSETS / "companion.css").read_text(encoding="utf-8")
    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(plain(meta["title"]))}</title>
<style>{css}</style>
</head>
<body>
<main class="wrap">
<article data-canonical-content="true">
<header class="opening">
{f'<p class="kicker" data-supporting>{kicker}</p>' if kicker else ''}
<h1>{inline(meta["title"])}</h1>
{question}
{render_flow(opening)}
</header>
{sections}
<footer class="colophon"><p>الشرح ده مبني على: {source}. <a class="nw" href="{html.escape(meta["url"], quote=True)}">المصدر الأصلي</a></p></footer>
</article>
</main>
</body>
</html>
"""


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    work = Path(sys.argv[1]).resolve()
    source_md = work / "companion.md"
    if not source_md.exists():
        print(f"missing {source_md}; write the teaching there first (references/format.md)", file=sys.stderr)
        return 2
    source_words = None
    manifest = work / "source-extraction.json"
    if manifest.exists():
        source_words = json.loads(manifest.read_text(encoding="utf-8")).get("word_count")
    elif (work / "source.txt").exists():
        source_words = len(WORD.findall((work / "source.txt").read_text(encoding="utf-8")))
    try:
        meta, opening, units = parse(source_md.read_text(encoding="utf-8"))
        check(opening, units)
        document = page(meta, opening, units)
    except BuildError as error:
        print(json.dumps({"ok": False, "error": str(error), "next": "fix companion.md at that line and run build_companion.py again"}, ensure_ascii=False))
        return 1
    out = work / "companion.html"
    out.write_text(document, encoding="utf-8")
    words = len(WORD.findall(text_of(opening) + " " + " ".join(u["title"] + " " + text_of(u["body"]) for u in units)))
    print(json.dumps({"ok": True, "html": str(out), "units": len(units), "words": words, "source_words": source_words,
        "next": "run_workflow.py finish (or publish) with the same --workdir"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
