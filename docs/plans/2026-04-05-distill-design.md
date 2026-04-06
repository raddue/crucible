---
ticket: "#111"
title: "Distill Skill — Convert Heavy Documents to Token-Efficient Formats"
date: "2026-04-05"
source: "spec"
---

# Distill Skill — Design Document

**Goal:** Create a `/distill` skill that converts heavy document formats (PDF, Word, Excel, PowerPoint, and 10+ others) into token-efficient representations (Markdown, CSV) for LLM consumption, with a structurally-aware digest pass that compresses to 20-30% of token count.

**Core insight:** Source files are fine to commit — they're just bytes on disk. The expensive part is when Claude needs to *read* them. A 50-page PDF burns thousands of tokens on layout artifacts, repeated headers, and formatting noise. Distill creates lightweight representations so downstream skills consume document content without blowing the context budget.

## 1. Current State Analysis

No document conversion capability exists in the Crucible skill framework today. When Claude encounters a PDF, Word doc, or spreadsheet, it either:
- Reads the raw file (expensive, lossy for binary formats)
- Asks the user to convert manually
- Skips the content entirely

**System tools available (verified on current environment):**

| Tool | Version | Capability |
|---|---|---|
| `pandoc` | 3.1.3 | Native conversion for 10+ document formats to Markdown |
| `pdftotext` | 24.02.0 (Poppler) | PDF to structured text with layout preservation |
| `python3` | 3.12.3 | Runtime for specialized libraries |
| `pip3` + `venv` | Available | Isolated dependency management |

**Dispatch convention:** All subagent dispatches (PDF structuring pass, digest pass) follow `shared/dispatch-convention.md` — disk-mediated dispatch with dispatch files written to `/tmp/crucible-dispatch-<session-id>/`, manifest logging, and pointer prompts.

## 2. Target State

A standalone `/distill` skill that:
1. Accepts one or more file paths (or a directory)
2. Detects format and routes through the appropriate conversion tier
3. Produces `.md` (or `.csv` for spreadsheets) intermediate representations
4. Runs a digest pass on converted files over 500 words, producing `.digest.md` at 20-30% of token count
5. Reports conversion summary with token savings metrics

### Output File Placement

Converted files are placed **alongside the source file** with the appropriate extension appended:

```
report.pdf       → report.md + report.digest.md
data.xlsx        → data-sheet1.csv + data-sheet2.csv + data.digest.md
slides.pptx      → slides.md + slides.digest.md
```

Source files are never modified or deleted.

### Generated File Handling

Converted files (`.md`, `.digest.md`, `.csv`) are working artifacts, not source files. The skill does not modify `.gitignore` — the user decides whether to track, ignore, or clean up generated files. The conversion summary includes a reminder: "Generated files can be added to .gitignore if not needed in version control."

## 3. Architecture: Three Conversion Tiers

The tiered design minimizes dependencies — most formats need only pandoc (already installed). Heavier tools are loaded only when needed.

### Tier 1: Pandoc-Native (10 formats, single command each)

| Extension | Format | Pandoc `-f` flag |
|---|---|---|
| `.docx` | Word | `docx` |
| `.rtf` | Rich Text | `rtf` |
| `.html`/`.htm` | HTML | `html` |
| `.odt` | OpenDocument Text | `odt` |
| `.epub` | EPUB | `epub` |
| `.rst` | reStructuredText | `rst` |
| `.org` | Org-mode | `org` |
| `.tex` | LaTeX | `latex` |
| `.ipynb` | Jupyter Notebook | `ipynb` |

**Conversion command pattern:**
```bash
pandoc -f "$FORMAT" -t markdown --wrap=none "$INPUT_PATH" -o "$OUTPUT_PATH"
```

All paths passed via shell variables, never inline interpolation.

### Tier 2: PDF (pdftotext + Claude structuring pass)

PDFs are structurally ambiguous — columns, headers, footers, page breaks all collapse into a flat text stream. Two-step conversion:

1. **Extract:** `pdftotext -layout "$INPUT_PATH" "$OUTPUT_PATH"` — preserves spatial layout
2. **Structure:** Dispatch a Sonnet agent to identify headings, lists, tables, and code blocks from the layout-preserved text. Produces clean Markdown with recovered structure.

**Why not pandoc for PDF?** Pandoc's PDF reader requires `pdftotext` anyway (it shells out to it) and adds no structuring. Going direct with pdftotext + Claude structuring gives better results.

**Scanned PDF detection:** After pdftotext, if the output is empty or near-empty (< 50 characters per page average), the PDF is likely scanned/image-based. Report: "This PDF appears to be scanned/image-based. Text extraction produced minimal content. Consider OCR processing externally before distilling."

### Tier 3: Python Venv (2 formats requiring specialized libraries)

| Extension | Library | Pin |
|---|---|---|
| `.pptx` | `python-pptx` | `1.0.2` |
| `.xlsx` | `openpyxl` | `3.1.5` |

**Why not pandoc for these?**
- **PPTX:** Pandoc 3.1.3 does not support pptx as an input format (`pandoc --list-input-formats` does not include `pptx`). `python-pptx` provides full access to slide structure, speaker notes, and layout metadata.
- **XLSX:** Pandoc has no xlsx support. `openpyxl` reads cells, formulas, and sheet structure.

**Venv management:**
1. Check for existing venv at `/tmp/crucible-distill-venv/`
2. If missing or corrupted: `python3 -m venv /tmp/crucible-distill-venv/`
3. Install pinned deps: `pip install python-pptx==1.0.2 openpyxl==3.1.5`
4. Execute conversion scripts via the venv's Python

**PPTX conversion output:** Slide-structured Markdown:
```markdown
## Slide 1: [Title]
[Content]

> Speaker notes: [notes if present]

---

## Slide 2: [Title]
[Content]
```

**XLSX conversion output:**
- One CSV file per sheet: `{basename}-{sheetname}.csv`
- Sheet count guard: if >20 sheets, warn and convert only the first 20
- Formula-cell warning: if >30% of cells contain formulas, warn that values may differ from displayed results. Note: openpyxl with `data_only=True` reads *cached* formula results from the last Excel save — if a file was created programmatically and never opened in Excel/LibreOffice, formula cells return `None`. If formula cells return `None`, emit a per-file warning: "Spreadsheet contains formulas with no cached values. Open and save in Excel/LibreOffice before distilling for accurate results."

### Unsupported Formats (with actionable guidance)

| Extension | Guidance |
|---|---|
| `.xls` | "Legacy Excel format. Export as .xlsx from Excel/LibreOffice, then re-run /distill." |
| `.ods` | "OpenDocument Spreadsheet. Export as .xlsx or .csv, then re-run /distill." |
| `.odp` | "OpenDocument Presentation. Export as .pptx, then re-run /distill." |
| `.key` | "Apple Keynote. Export as .pptx from Keynote, then re-run /distill." |
| `.numbers` | "Apple Numbers. Export as .xlsx from Numbers, then re-run /distill." |
| `.pages` | "Apple Pages. Export as .docx from Pages, then re-run /distill." |

## 4. Digest Pass (Core Value Proposition)

The full `.md` conversion is the intermediate step. The `.digest.md` is what downstream skills actually consume — a structurally-aware compression at 20-30% of token count.

**Principle:** Distill, do not concatenate. Preserve structure and key content. Eliminate redundancy, boilerplate, and formatting noise.

### When to digest

- Converted `.md` files **over 500 words** get a digest pass
- Files under 500 words are already compact — the full `.md` is the digest
- CSV files do not get a digest (tabular data doesn't compress well semantically)

### Digest agent

**Model:** Sonnet (transformation task, not creative reasoning)
**Input:** Full converted `.md` content
**Output:** `.digest.md` at 20-30% of input token count

**Digest instructions:**
1. Preserve document structure (headings, hierarchy)
2. Preserve key data: names, numbers, decisions, constraints, code blocks
3. Eliminate: repeated headers/footers, boilerplate language, redundant examples, verbose explanations where a summary suffices
4. Preserve tables in full if they contain data; summarize if they contain prose
5. For slide decks: preserve title + key points per slide, collapse "thank you" / "questions" slides
6. Output must stand alone — a reader should understand the document's substance without the original

### Digest quality metric

The orchestrator verifies the digest is within the 20-30% target range (by word count as a proxy for token count). If the digest exceeds 35%, re-dispatch with stricter compression instructions. If below 15%, re-dispatch with "preserve more detail" instructions. One retry only — the second result is accepted regardless.

## 5. Pre-Flight Checks

Before converting any file, run safety checks:

### Zip Bomb Detection (docx, pptx, xlsx)

Office formats are ZIP archives. Check uncompressed size before extraction:
```bash
unzip -l "$INPUT_PATH" | tail -1  # Total uncompressed size
```
If uncompressed size exceeds 500MB, abort: "File uncompressed size ({size}) exceeds safety limit. Skipping."

### PDF Attachment Detection

Check for embedded files in PDFs:
```bash
pdfdetach -list "$INPUT_PATH" 2>/dev/null
```
If attachments found, warn: "PDF contains {N} embedded attachments. These are not extracted by distill — only the text content is converted."

### Encoding Validation

After conversion, verify output is valid UTF-8. If conversion produces non-UTF-8 output, attempt re-encoding from detected charset. If re-encoding fails, report the encoding issue and skip the file.

## 6. Key Design Decisions

### DEC-1: python-pptx for PPTX (High confidence)

**Decision:** Use python-pptx (Tier 3) for PPTX conversion.

**Alternatives considered:**
- Pandoc: pandoc 3.1.3 does not support pptx as an input format — not a viable alternative
- python-pptx: Preserves slide boundaries, speaker notes, layout metadata

**Reasoning:** python-pptx is the only viable option that preserves slide structure. The venv cost is minimal (one-time setup, cached in /tmp).

### DEC-2: Output placement alongside source files (High confidence)

**Decision:** Write converted files next to their sources, not in a separate output directory.

**Alternatives considered:**
- Separate output directory (e.g., `distilled/`): Cleaner separation but harder to find converted files
- Alongside source: Easy discovery, clear association between source and output

**Reasoning:** The converted file is a view of the source. Placing them together makes the association obvious. No directory creation needed.

### DEC-3: Digest as primary output, full .md as intermediate (High confidence)

**Decision:** The `.digest.md` is the skill's primary deliverable. The full `.md` is kept for reference but downstream skills should consume the digest.

**Reasoning:** Token efficiency is the entire point. A 50-page PDF → 15-page .md → 4-page .digest.md. Downstream skills consuming the digest save ~80% of context budget compared to the full conversion.

### DEC-4: No batch parallelism for conversion (Medium confidence)

**Decision:** Convert files sequentially within a single invocation. Dispatch digest agents sequentially.

**Alternatives considered:**
- Parallel conversion via Agent Teams: Faster for large batches
- Sequential: Simpler, avoids venv contention, sufficient for typical use (1-5 files)

**Reasoning:** Most invocations process 1-3 files. The conversion step is fast (pandoc/pdftotext are sub-second). Only the digest pass is slow (LLM dispatch), and parallelizing LLM calls risks context exhaustion for the orchestrator tracking multiple digest results. Sequential is correct for v1; parallel can be added if batch sizes warrant it.

### DEC-5: Venv in /tmp, not project-local (High confidence)

**Decision:** Python venv at `/tmp/crucible-distill-venv/`, not in the project directory.

**Reasoning:** The venv is a tool, not a project artifact. Placing it in /tmp avoids polluting the project directory, avoids gitignore entries, and is consistent with other Crucible temp artifacts (dispatch files, etc.). The venv is recreated if missing — no durability needed.

## 7. Risk Areas

| Risk | Severity | Mitigation |
|---|---|---|
| Pandoc not installed on target system | High | Pre-flight tool check. Clear error: "pandoc not found. Install with: apt install pandoc" |
| pdftotext not installed | Medium | Pre-flight check. Graceful degradation: skip PDF conversion with guidance |
| Python deps fail to install (network, permissions) | Medium | Cache venv, pin versions, clear error message with manual install instructions |
| Scanned PDFs produce empty output | Low | Detection + user guidance (see Tier 2 design) |
| Very large files exhaust digest agent context | Medium | v1: hard cap at 50K words per file — report "File exceeds 50K word limit for digest pass. Consider splitting the document." Chunked digestion deferred to v2. |
| Office format corruption / password protection | Low | Catch conversion errors, report per-file, continue with remaining files |

## 8. Acceptance Criteria

1. Skill definition at `skills/distill/SKILL.md` with tiered architecture
2. Tier 1: Pandoc-native conversions for docx, rtf, html, odt, epub, rst, org, tex, ipynb
3. Tier 2: PDF to structured markdown with heading detection, UTF-8 encoding, scanned PDF detection
4. Tier 3a: PPTX to slide-structured markdown via python-pptx
5. Tier 3b: XLSX to CSV (one file per sheet, formula-cell warning, sheet count guard)
6. Digest pass: `.digest.md` at 20-30% token count for all converted `.md` files over 500 words
7. Pre-flight: zip bomb detection, PDF attachment detection, encoding validation
8. Unsupported formats reported with actionable guidance
9. Shell safety: all file paths via quoted shell variables (e.g., `"$INPUT_PATH"`), no inline interpolation
10. Conversion summary with token savings metrics
11. No source files modified or deleted
12. Tool availability checks with clear install guidance on failure
