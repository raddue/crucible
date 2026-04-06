---
name: distill
description: "Convert heavy document formats (PDF, Word, Excel, PowerPoint, and 10+ others) to token-efficient Markdown/CSV with structurally-aware digest compression. Use when Claude needs to read documents without burning excessive context budget. Triggers on /distill, 'distill this', 'convert to markdown', 'make this readable'."
---

# Distill

## Overview

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

Convert heavy document formats to token-efficient representations (Markdown, CSV) for LLM consumption. The core deliverable is the `.digest.md` — a structurally-aware compression at 20-30% of token count.

**Skill type:** Rigid — follow exactly, no shortcuts.

**Models:**
- PDF structuring agent: Sonnet
- Digest agent: Sonnet
- Orchestrator: runs on whatever model the session uses

**Announce at start:** "I'm using the distill skill to convert documents to token-efficient formats."

## Invocation API

```
/distill <path> [path2 ...]
/distill <directory>
```

**Examples:**
- `/distill docs/report.pdf` — convert one file
- `/distill docs/report.pdf data/sheet.xlsx slides/deck.pptx` — convert multiple files
- `/distill docs/` — convert all supported files in directory (single-level, not recursive)

Mixed mode is supported: `/distill docs/ extra/report.pdf`

## The Process

Execute phases in this order. Each phase completes for all files before the next begins.

### Phase 0: Tool Availability Check

At skill start, before processing any files, check for required tools:

| Check | Command | If Missing |
|---|---|---|
| **Tier 1** | `which pandoc` | "pandoc not found. Install: `apt install pandoc` (Debian/Ubuntu) or `brew install pandoc` (macOS). Tier 1 formats will be skipped." |
| **Tier 2** | `which pdftotext` | "pdftotext not found. Install: `apt install poppler-utils` (Debian/Ubuntu) or `brew install poppler` (macOS). PDF conversion will be skipped." |
| **Tier 3** | `which python3` | "python3 not found. PPTX and XLSX conversion will be skipped." |
| **Pre-flight** | `which unzip` | Skip zip bomb detection with note. Not a conversion blocker. |
| **Pre-flight** | `which pdfdetach` | Skip PDF attachment detection with note. Not a conversion blocker. |

Build a set of available tiers. Route files only to available tiers. Files targeting unavailable tiers get routed to unsupported-with-guidance (Phase 1b).

### Phase 1: Input Resolution

#### 1a: Build File List

**Individual file paths:** Use directly. Verify each file exists.

**Directory paths:** Single-level glob for files with supported extensions (not recursive). Build file list sorted alphabetically. Report: "Found {N} convertible files in {directory}: {list}."

Supported extensions for glob: `.pdf`, `.docx`, `.rtf`, `.html`, `.htm`, `.odt`, `.epub`, `.rst`, `.org`, `.tex`, `.ipynb`, `.pptx`, `.xlsx`

**Mixed mode:** Process both directory globs and individual paths. Deduplicate by absolute path.

#### 1b: Route Files to Tiers

For each file, determine the conversion tier by extension:

| Extension | Tier | Format Flag |
|---|---|---|
| `.docx` | 1 | `docx` |
| `.rtf` | 1 | `rtf` |
| `.html` | 1 | `html` |
| `.htm` | 1 | `html` |
| `.odt` | 1 | `odt` |
| `.epub` | 1 | `epub` |
| `.rst` | 1 | `rst` |
| `.org` | 1 | `org` |
| `.tex` | 1 | `latex` |
| `.ipynb` | 1 | `ipynb` |
| `.pdf` | 2 | — |
| `.pptx` | 3 | — |
| `.xlsx` | 3 | — |

**Unsupported formats:** Output actionable guidance per this table, then continue with remaining files:

| Extension | Guidance |
|---|---|
| `.xls` | "Legacy Excel format. Export as .xlsx from Excel/LibreOffice, then re-run /distill." |
| `.ods` | "OpenDocument Spreadsheet. Export as .csv (single-sheet) or .xlsx (multi-sheet), then re-run /distill." |
| `.odp` | "OpenDocument Presentation. Export as .pptx, then re-run /distill." |
| `.key` | "Apple Keynote. Export as .pptx from Keynote, then re-run /distill." |
| `.numbers` | "Apple Numbers. Export as .xlsx from Numbers, then re-run /distill." |
| `.pages` | "Apple Pages. Export as .docx from Pages, then re-run /distill." |

**Unknown extensions:** "Unsupported format: {ext}. Supported formats: docx, rtf, html, odt, epub, rst, org, tex, ipynb, pdf, pptx, xlsx."

**Unavailable tier:** If a file's tier is unavailable (tool missing from Phase 0), report: "{file}: requires {tool} (not installed). Skipping."

### Phase 2: Pre-Flight Checks

Run per-file safety checks before conversion. Failures are per-file — do not halt the batch.

#### Zip Bomb Detection (docx, pptx, xlsx)

Office formats are ZIP archives. If `unzip` is available:

```bash
UNCOMPRESSED=$(unzip -l "$INPUT_PATH" 2>/dev/null | tail -1 | awk '{print $1}')
```

If uncompressed size exceeds 500MB (524288000 bytes), abort this file: "File uncompressed size ({size}) exceeds 500MB safety limit. Skipping."

If `unzip` is not available, skip this check (noted in Phase 0).

#### PDF Attachment Detection

For PDF files, if `pdfdetach` is available:

```bash
ATTACHMENTS=$(pdfdetach -list "$INPUT_PATH" 2>/dev/null | grep -c "^[0-9]")
```

If attachments found, warn: "PDF contains {N} embedded attachments. These are not extracted — only text content is converted." Continue with conversion.

#### Encoding Validation

After conversion (not before), verify output is valid UTF-8:

```bash
file --mime-encoding "$OUTPUT_PATH"
```

If not UTF-8, attempt re-encoding: `iconv -f <detected-charset> -t UTF-8 "$OUTPUT_PATH" -o "$OUTPUT_PATH.tmp" && mv "$OUTPUT_PATH.tmp" "$OUTPUT_PATH"`. If re-encoding fails, report and skip.

### Phase 3: Conversion

Process files sequentially. For each file:

#### Tier 1: Pandoc-Native

```bash
INPUT_PATH="$1"
OUTPUT_PATH="${INPUT_PATH%.*}.md"
FORMAT="$2"  # from routing table

pandoc -f "$FORMAT" -t markdown --wrap=none "$INPUT_PATH" -o "$OUTPUT_PATH"
```

**Shell safety:** All file paths via quoted shell variables. Never inline interpolation. Never use unquoted `$()` or backtick interpolation of file paths.

**Error handling:**
- Non-zero exit code: report "pandoc conversion failed for {file}: {error}" and continue
- Empty output: report "pandoc produced empty output for {file}" and continue

**Idempotency:** Overwrites existing output files without warning.

#### Tier 2: PDF (pdftotext + Claude structuring)

**Step 1 — Extract:**
```bash
INPUT_PATH="$1"
TEXT_PATH="${INPUT_PATH%.*}.txt"
OUTPUT_PATH="${INPUT_PATH%.*}.md"

pdftotext -layout "$INPUT_PATH" "$TEXT_PATH"
```

**Scanned PDF detection:** Count total characters and pages:
```bash
CHARS=$(wc -c < "$TEXT_PATH")
PAGES=$(pdfinfo "$INPUT_PATH" 2>/dev/null | grep "^Pages:" | awk '{print $2}')
```
If `pdfinfo` is unavailable, estimate pages from `pdftotext` output (count form-feed characters). If average chars/page < 50, report: "This PDF appears to be scanned/image-based. Text extraction produced minimal content. Consider OCR processing externally before distilling." Skip structuring pass. Clean up temp `.txt` file.

**Step 2 — Structure:** Dispatch a Sonnet agent using `skills/distill/pdf-structurer-prompt.md` to transform the raw pdftotext output into clean Markdown with recovered headings, lists, tables, and code blocks. Write result to `OUTPUT_PATH`. Clean up temp `.txt` file.

#### Tier 3: Python Venv

**Venv setup (once per invocation, only if Tier 3 files exist):**

```bash
VENV="/tmp/crucible-distill-venv"

# Health check
if [ -d "$VENV" ]; then
    "$VENV/bin/python3" -c "import sys" 2>/dev/null || rm -rf "$VENV"
fi

# Create if missing
if [ ! -d "$VENV" ]; then
    echo "Installing Python dependencies (one-time setup, ~15 seconds)..."
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet python-pptx==1.0.2 openpyxl==3.1.5
    if [ $? -ne 0 ]; then
        echo "Failed to install Python dependencies."
        echo "Manual install: pip install python-pptx==1.0.2 openpyxl==3.1.5"
        echo "PPTX and XLSX conversion will be skipped."
        # Route remaining Tier 3 files to unsupported
        return
    fi
fi
```

**PPTX conversion:**
```bash
"$VENV/bin/python3" skills/distill/convert_pptx.py --input "$INPUT_PATH" --output "$OUTPUT_PATH"
```

**XLSX conversion:**
```bash
"$VENV/bin/python3" skills/distill/convert_xlsx.py --input "$INPUT_PATH" --output-dir "$(dirname "$INPUT_PATH")"
```

Output: one CSV per sheet at `{basename}-{sheetname}.csv`. Sheetnames sanitized (spaces → hyphens, special chars stripped).

### Phase 4: Digest Pass

After all conversions complete, run the digest pass on eligible files.

**Eligibility:**
- File is `.md` (not `.csv`)
- Word count > 500 words
- Word count ≤ 50,000 words (hard cap — report "File exceeds 50K word limit for digest pass. Consider splitting the document." for larger files)

**Dispatch:** For each eligible file, dispatch a Sonnet digest agent using `skills/distill/digest-prompt.md`. Before dispatching, fill template placeholders: replace `{{ORIGINAL_WORDS}}` with the converted file's word count and `{{TARGET_WORDS}}` with 25% of that count. The raw pdftotext output (for `pdf-structurer-prompt.md`) or converted `.md` content (for `digest-prompt.md`) is included as a content block below the prompt template in the dispatch file.

**Quality check:** After the digest agent returns, count words in the digest:
- If digest is 15-35% of input word count: accept
- If digest exceeds 35%: re-dispatch with "Compress more aggressively. Target 20-25% of the original word count."
- If digest is below 15%: re-dispatch with "Preserve more detail. Target 25-30% of the original word count."
- One retry only. Second result accepted regardless.

**Output:** Write digest to `{original-path-without-ext}.digest.md`.

Word count is a proxy for token count. These diverge for code-heavy or CJK content, but word count is sufficient for v1.

### Phase 5: Summary

After all conversions and digests complete, output:

```
## Distill Summary

| File | Format | Tier | Converted | Digest | Token Savings |
|---|---|---|---|---|---|
| {file} | {format} | {tier} | {output} ({words} words) | {digest} ({words} words) | ~{pct}% |

**Total:** {N} files converted, {M} digests produced, ~{pct}% average token savings on digestible content.
Generated files can be added to .gitignore if not needed in version control.
```

Token savings per file = `1 - (digest words / converted words)` expressed as percentage.

Files that were skipped (unsupported, tool missing, pre-flight failure) are listed separately:

```
**Skipped:** {N} files
- {file}: {reason}
```

## Shell Safety (Non-Negotiable)

Every Bash command that touches file paths MUST use quoted shell variables:

```bash
# CORRECT
pandoc -f "$FORMAT" -t markdown --wrap=none "$INPUT_PATH" -o "$OUTPUT_PATH"

# WRONG — never do this
pandoc -f $FORMAT -t markdown --wrap=none $INPUT_PATH -o $OUTPUT_PATH
```

- All paths passed as `"$VAR"`, never bare `$VAR`
- No unquoted `$()` or backtick interpolation of paths
- Python scripts receive paths via argparse, not shell interpolation
- Source files are NEVER modified or deleted

## Error Handling

| Failure | Behavior |
|---|---|
| Tool not installed | Skip tier, report with install guidance, continue |
| Conversion fails (non-zero exit) | Report per-file, continue with remaining files |
| Empty conversion output | Report per-file, continue |
| Zip bomb detected | Skip file, report, continue |
| Scanned PDF | Report, skip digest, continue |
| Venv/pip failure | Skip Tier 3, report with manual install instructions |
| Digest out of range | One retry, accept second result regardless |
| File not found | Report, continue with remaining files |
| Permission denied | Report, continue |
| Encoding error | Attempt re-encode, skip on failure, continue |

**Principle:** Never halt the batch for a single file failure. Report and continue.

## Integration

**Standalone usage:**
- `/distill <path>` — convert one or more files
- `/distill <directory>` — convert all supported files in directory

**Called by:**
- Any skill that needs to read heavy document formats
- User directly when preparing documents for LLM consumption

**Dispatches:**
- PDF structuring agent (Sonnet) via `skills/distill/pdf-structurer-prompt.md`
- Digest agent (Sonnet) via `skills/distill/digest-prompt.md`

**Does not dispatch:** No quality gate, no red-team, no review loop. Distill is a utility skill — it converts and compresses. Quality is ensured by the digest quality metric (word count check + one retry).
