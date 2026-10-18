# companion.md format

Plain Markdown plus a few `:::` blocks. `scripts/build_companion.py WORKDIR` renders it into the fixed Compass design; raw HTML stops the build.

```markdown
---
title: عنوان عربي بيقول الفكرة
source_title: The exact source title
creator: Author or speaker
kind: video            # video | article | book | chapter | podcast | lecture | paper | talk
url: https://the-original-link
---

:::thesis
سؤال المصدر وإجابته في جملة أو اتنين.
:::

## أول فكرة، مكتوبة كجملة بتقول الفكرة
الشرح…

## الفكرة التانية
…
```

- `title`, `source_title` and `url` are required; the source line and original link are added automatically.
- Exactly one `:::thesis` before the first `##`. Each `##` is a unit (the reader pages through units); `###` is a sub-point. No `#`.
- Inline: `**bold**`, `*emphasis*`, `` `code` ``, `[label](https://…)`. Lists, `> ` quotes (last line `> — who` is the attribution) and pipe tables (optional `جدول: caption` line above) work as normal.

## Blocks

Open with `:::name`, close with `:::`; blocks don't nest.

| Block | For | Contents |
| --- | --- | --- |
| `:::compare` | 2–3 positions on the same question | `### side` then paragraphs |
| `:::steps` / `:::steps proposed` | a real order or causal chain (proposed = hypothesised, drawn dashed) | `1. **label** — detail` |
| `:::bars 100 %` | the source's quantities on one scale (max, unit) | `- label \| value \| note`, optional `caption: …` |
| `:::stats` | 2–4 headline numbers | `- 49% \| what it measures` |
| `:::timeline` | dated events | `- 1998 \| what happened` |
| `:::terms` | key terms, once, early | `- **المصطلح** (English): المعنى` |
| `:::key` | the one thing to hold on to | paragraphs |
| `:::limit` | a caveat the source states | paragraphs |
| `:::example` / `:::example added` | the source's example / one you added | paragraphs, lists |
| `:::added` | explanation beyond the source | paragraphs |

The build stops only on broken format (bad front matter, unclosed or unknown block, bar outside its scale, wrong item counts), raw HTML, emoji and canned filler phrases; the error names the line.
