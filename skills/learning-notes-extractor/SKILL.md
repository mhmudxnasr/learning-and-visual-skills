---
name: learning-notes-extractor
description: Extracts text and handwritten annotations from any PDF, HTML, or study guide, compiles them into an Influence-style markdown note (bilingual English/Egyptian Arabic slang), automatically routes the note into its exact Taste Map category path under `07 - 🎓 Learning`, embeds source attachments in `z - 📎 Attachments`, updates `00 - Table of Contents.md`, syncs `Taste Map/Recommendations  — Mahmood.md`, and includes a `📝 My Notes & Reaction` block for `taste-mapper`. Trigger whenever asked to "make notes", "extract notes", "take notes", process a study guide/HTML/PDF, or via `/learning-notes-extractor`.
---

# Learning Notes Extractor

This skill extracts text and handwritten annotations from a PDF or HTML document and formats them into an Obsidian-ready markdown file. It automatically resolves the topic against `Taste Map/Map.canvas`, places the note and its source attachments into the correct folder path in `07 - 🎓 Learning`, updates the central Table of Contents (`00 - Table of Contents.md`), syncs recommendations, and provides a `📝 My Notes & Reaction` field for the `taste-mapper` skill to read.

## Core Workflow

1. **Scan the Document & OCR Fallback:**
   - Read the file (PDF or HTML) using `view_file`. Pay close attention to text, quotes, and handwritten annotations.
   - **OCR Fallback:** If handwritten margin notes or scanned PDF pages are low-contrast or illegible with `view_file`, trigger `ocr-and-documents` (PyMuPDF / Tesseract) to extract precise text overlays.

2. **Identify Context & Topic Mapping:**
   - Check `Taste Map/Map.canvas` or `/home/mahmud/Documents/Obsidian Vault/07 - 🎓 Learning/` to find the exact `<Category>/<Branch>/<Leaf>` node matching the document's topic.
   - Create missing category/branch/leaf folders on demand when saving notes.

3. **Attachment Handling:**
   - Copy the source file (HTML, PDF, image) into:
     1. `/home/mahmud/Documents/Obsidian Vault/z - 📎 Attachments/[Source_Filename]`
     2. `/home/mahmud/Documents/Obsidian Vault/07 - 🎓 Learning/z - 📎 Attachments/<Category>/<Branch>/<Leaf>/[Source_Filename]`

4. **Format the Summary & Reaction Block:**
   - Place a `📝 My Notes & Reaction` callout block directly under the title `# [Document Title]` so `taste-mapper` can parse user feedback.
   - Merge academic English text with expressive Egyptian Arabic slang interpretations, weaving handwritten insights natively into the Arabic summaries.

5. **Save Note to Vault & Completed Folder:**
   - Save the markdown note to:
     - `/home/mahmud/Documents/Obsidian Vault/07 - 🎓 Learning/<Category>/<Branch>/<Leaf>/[Document Title].md`
     - `/home/mahmud/completed/[Document Title].md`

6. **Recommendations Auto-Sync (`Recommendations  — Mahmood.md`):**
   - If the note comes from a primary research piece (book, paper, podcast, lecture), check `/home/mahmud/Documents/Obsidian Vault/Taste Map/Recommendations  — Mahmood.md`.
   - Append or update the entry under `Active leaves` following `Schema.md` (video_title, creator, video_url, why_this, verified, status=active, user_rating=unset, dedup_key).

7. **Update Central Table of Contents (`00 - Table of Contents.md`):**
   - Append an entry for the newly processed note to `/home/mahmud/Documents/Obsidian Vault/07 - 🎓 Learning/00 - Table of Contents.md`.
   - Format:
     ```markdown
     ### <Category> / <Branch> / <Leaf>

     #### [[Document Title]]
     > **Summary:** [Concise 2-3 sentence summary of the core thesis, empirical studies, and takeaways].
     > **Path:** `07 - 🎓 Learning/<Category>/<Branch>/<Leaf>/[Document Title].md`
     > **Attachment:** `![[Source_Filename]]`

     ---
     ```

## Formatting Rules & Template

**Strict Rule:** DO NOT USE YAML FRONTMATTER. The file must start directly with an H1 heading.

Follow this structure exactly:

```markdown
# [Chapter/Document Title]

> [!NOTE] 📝 My Notes & Reaction
> *[Write your thoughts, reaction (loved/hated/mid), or personal takeaways here. The taste-mapper skill in Hermes reads this section to update your Taste Map profile.]*

#### THE FOUNDATION

> [!NOTE] [Core Concept Title]
> "[Quote from the text or core definition]"

*[Egyptian Arabic slang summary of the foundation. Integrate relevant handwritten notes here, keeping them natural and punchy.]*

---

#### KEY CASE STUDIES

**[Study Name]:** 
[Brief English summary of the study methodology and statistical results, e.g., ==$5,000==].

*[Egyptian Arabic slang explanation of the study's implications. Weave in the handwritten notes corresponding to this study.]*

**[Another Study Name]:** 
[Brief English summary...]

*[Egyptian Arabic slang explanation...]*

---

#### HOW IT'S EXPLOITED: VULNERABILITIES OF THE RULE

> [!WARNING] [Vulnerability/Tactic Name]
> [Brief English description of how the concept is weaponized or how humans fail to control it.]

*[Egyptian Arabic breakdown of the trick or vulnerability, using terms from the user's handwriting if available.]*

---

#### DEFENSE & HOW TO SAY NO - ازاي تحمي نفسك

**1. [Strategy 1]:** [Brief English explanation].
**2. [Strategy 2]:** [Brief English explanation].

> [!TIP] الخلاصة وطريقة الحماية
> *[Egyptian Arabic final advice on how to defend against this vulnerability. Heavily incorporate the user's handwritten "takeaways" or "My Take" sections here.]*

----
	![[Source_Filename.html]]
```

## Tone & Integration of Handwriting

- **Egyptian Slang:** Use words like "من الآخر", "عشان", "بضان", "اشتغالة", "سالكة", "بيكرف".
- **Handwriting Priority:** The user's handwritten notes are the MOST IMPORTANT part of the summary. If the user wrote an insight, this perspective MUST drive the Arabic commentary for that section.
- **Italics:** All Arabic commentary must be enclosed in italics `*...*`.
- **Bilingual Mixing:** It's okay to mix English words into the Arabic text exactly as the user did in their handwriting (e.g., `(100% agree)`).
- **Attachment Link:** Always end the file with `----` followed by `\t![[Source_Filename]]` so Obsidian embeds and links the source document seamlessly.
