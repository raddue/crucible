---
ticket: "#111"
title: "Distill Skill — Implementation Plan"
date: "2026-04-05"
source: "spec"
---

# Distill Skill — Implementation Plan

## Task Overview

9 tasks (plus 3b) across 3 waves. Wave 1 is the skill skeleton + Tier 1 (pandoc) + tool checks + input handling. Wave 2 adds Tier 2 (PDF) + Tier 3 (Python venv). Wave 3 adds the digest pass + pre-flight checks + integration.

## Wave 1: Skill Skeleton + Tier 1

### Task 1: Create SKILL.md and skill directory structure

**Files:** `skills/distill/SKILL.md`
**Complexity:** Medium
**Dependencies:** None

Create the skill definition with:
- YAML frontmatter (`name: distill`, description with trigger words)
- Overview section with `<!-- CANONICAL: shared/dispatch-convention.md -->` reference
- Announce text: "I'm using the distill skill to convert documents to token-efficient formats."
- Invocation API: `/distill <path> [path2 ...]` or `/distill <directory>`
- Full phase breakdown (pre-flight → detect → convert → digest → report)
- Format routing table mapping extensions to tiers
- Shell safety requirements
- Error handling table
- Integration section

### Task 2: Implement Tier 1 pandoc conversion

**Files:** `skills/distill/SKILL.md` (conversion logic section), `skills/distill/pandoc-convert.sh` (optional helper)
**Complexity:** Low
**Dependencies:** Task 1

Implement the pandoc conversion path:
- Format detection from file extension
- Pandoc command construction with proper `-f` flag per format
- `--wrap=none` for all conversions (preserves line breaks)
- Output path computation (source path with `.md` extension appended)
- Error handling: pandoc not found, conversion failure, empty output
- All file paths via shell variables (no inline interpolation)

Note: The skill orchestrator runs pandoc directly via Bash tool. No subagent needed for Tier 1.

### Task 3: Implement tool availability pre-flight

**Files:** `skills/distill/SKILL.md` (tool check section)
**Complexity:** Low
**Dependencies:** Task 1

At skill start (before processing any files), check for required tools:
- **Tier 1:** `which pandoc` — if missing, report: "pandoc not found. Install with: `apt install pandoc` (Debian/Ubuntu) or `brew install pandoc` (macOS). Tier 1 formats (docx, rtf, html, odt, epub, rst, org, tex, ipynb) will be skipped."
- **Tier 2:** `which pdftotext` — if missing, report: "pdftotext not found. Install with: `apt install poppler-utils` (Debian/Ubuntu) or `brew install poppler` (macOS). PDF conversion will be skipped."
- **Tier 3:** `which python3` — if missing, report: "python3 not found. PPTX and XLSX conversion will be skipped."
- **Pre-flight tools:** `which unzip` (for zip bomb detection on Office formats), `which pdfdetach` (for PDF attachment detection, ships with poppler-utils). If missing, skip the respective pre-flight check with a note — these are safety checks, not conversion blockers.

Build a set of available tiers. Route files only to available tiers. Files targeting unavailable tiers get routed to unsupported-with-guidance.

### Task 3b: Implement directory-mode input

**Files:** `skills/distill/SKILL.md` (input handling section)
**Complexity:** Low
**Dependencies:** Task 1

When the user passes a directory path:
1. Single-level glob for files with supported extensions (not recursive — explicit paths for nested directories)
2. Build file list from glob results, sorted alphabetically
3. Report: "Found {N} convertible files in {directory}: {list}"
4. Process each file through the normal conversion pipeline

When the user passes individual file paths, use them directly. Mixed mode (files + directories) is supported.

### Task 4: Implement unsupported format handling

**Files:** `skills/distill/SKILL.md` (unsupported format section)
**Complexity:** Low
**Dependencies:** Task 1

Add the unsupported format guidance table. When a file's extension matches an unsupported format, output the specific conversion guidance (e.g., ".xls → export as .xlsx from Excel/LibreOffice"). Continue processing remaining files.

## Wave 2: Tier 2 + Tier 3

### Task 5: Implement Tier 2 PDF conversion

**Files:** `skills/distill/SKILL.md` (PDF section), `skills/distill/pdf-structurer-prompt.md`
**Complexity:** High
**Dependencies:** Task 1, Task 3 (tool check must confirm pdftotext available)

Two-step PDF conversion:
1. Run `pdftotext -layout` to extract text
2. Dispatch a Sonnet structuring agent to recover headings, lists, tables from the layout text

Create `pdf-structurer-prompt.md` dispatch template:
- Input: raw pdftotext output
- Instructions: identify headings (by capitalization, spacing, font-size-implied patterns), recover list structure, identify table boundaries, detect code blocks
- Output: clean Markdown with recovered structure
- Add the full dispatch comment header per `skills/shared/dispatch-convention.md`

Include scanned PDF detection: if pdftotext output averages < 50 chars/page, report as likely scanned.

### Task 6: Implement Tier 3 Python venv conversion

**Files:** `skills/distill/SKILL.md` (Tier 3 section), `skills/distill/convert_pptx.py`, `skills/distill/convert_xlsx.py`
**Complexity:** Medium
**Dependencies:** Task 1, Task 3 (tool check must confirm python3 available)

Implement venv management:
- Check for existing venv at `/tmp/crucible-distill-venv/`
- Health check: run `"$VENV/bin/python3" -c "import sys"` — if it fails (e.g., system Python upgraded, broken symlinks), recreate the venv
- Create if missing or unhealthy: `python3 -m venv /tmp/crucible-distill-venv/`
- Install pinned deps: `pip install python-pptx==1.0.2 openpyxl==3.1.5`
- **Error handling:** Check pip install exit code. On failure (no network, proxy, permissions), report: "Failed to install Python dependencies. Manual install: `pip install python-pptx==1.0.2 openpyxl==3.1.5`. PPTX and XLSX conversion will be skipped." Route pptx/xlsx files to unsupported-with-guidance.
- **UX:** If venv creation is needed, announce: "Installing Python dependencies (one-time setup, ~15 seconds)..."

Create conversion scripts:
- `convert_pptx.py`: Read pptx, output slide-structured Markdown (slide title, content, speaker notes per slide, separated by `---`)
- `convert_xlsx.py`: Read xlsx, output one CSV per sheet with naming pattern `{basename}-{sheetname}.csv` (sheetname sanitized: spaces to hyphens, special chars stripped). Implement formula-cell warning (>30% formula cells), `None` value detection (write `#NO_CACHE` as the cell value in CSV output when formula cells return `None`, making data loss visible in the output itself; also warn that file needs to be opened in Excel first), and sheet count guard (max 20 sheets).

Both scripts accept input/output paths via command-line arguments (not env vars — Python argparse is safe). Scripts validate inputs and return non-zero on failure.

## Wave 3: Digest + Pre-Flight + Integration

### Task 7: Implement digest pass

**Files:** `skills/distill/SKILL.md` (digest section), `skills/distill/digest-prompt.md`
**Complexity:** High
**Dependencies:** Tasks 2, 5, 6

Create `digest-prompt.md` dispatch template:
- Input: full converted `.md` content
- Target: 20-30% of input word count
- Instructions per design doc section 4 (preserve structure, key data, eliminate redundancy)
- Add the full dispatch comment header per `skills/shared/dispatch-convention.md`

Implement digest orchestration in SKILL.md (routing logic):
- Word count check (skip files ≤500 words)
- Hard cap: reject files >50K words with guidance ("File exceeds 50K word limit for digest pass. Consider splitting the document."). Chunked digestion deferred to v2.
- Dispatch Sonnet digest agent
- Verify output is within 20-30% target (15-35% acceptable range)
- One retry if out of range (stricter or looser instructions)
- Second result accepted regardless

### Task 8: Implement pre-flight checks

**Files:** `skills/distill/SKILL.md` (pre-flight section)
**Complexity:** Medium
**Dependencies:** Task 1

Note: Pre-flight logic is described in SKILL.md and runs before any conversion (Tasks 2/5/6). This task writes the SKILL.md section; runtime ordering is: tool check → per-file pre-flight → convert → digest → report.

Implement three pre-flight checks:
1. **Zip bomb detection** (docx/pptx/xlsx): `unzip -l` to check uncompressed size. Abort if >500MB.
2. **PDF attachment detection**: `pdfdetach -list` to check for embedded files. Warn but continue.
3. **Encoding validation**: Post-conversion UTF-8 check. Attempt re-encoding on failure.

Pre-flight runs before conversion for each file. Failures are per-file (don't halt the batch).

### Task 9: Implement conversion summary and token metrics

**Files:** `skills/distill/SKILL.md` (summary section)
**Complexity:** Low
**Dependencies:** Tasks 2, 5, 6, 7

After all conversions complete, output a summary table:

```
## Distill Summary

| File | Format | Tier | Converted | Digest | Token Savings |
|---|---|---|---|---|---|
| report.pdf | PDF | 2 | report.md (4,200 words) | report.digest.md (1,100 words) | ~74% |
| data.xlsx | Excel | 3 | 3 sheets → CSV | — | — |
| slides.pptx | PPTX | 3 | slides.md (800 words) | — (under 500w) | — |

**Total:** 3 files converted, 1 digest produced, ~74% token savings on digestible content.
Generated files can be added to .gitignore if not needed in version control.
```

Token savings = `1 - (digest words / original converted words)`. Word count as a proxy for token count (close enough for reporting). Include .gitignore reminder per design doc.

## Dependency Graph

```
Task 1 (skeleton) ← Task 2 (Tier 1)
                  ← Task 3 (tool checks) + Task 3b (directory mode)
                  ← Task 4 (unsupported)
Task 1, Task 3    ← Task 5 (Tier 2)
Task 1, Task 3    ← Task 6 (Tier 3)
Task 2, 5, 6      ← Task 7 (digest)
Task 1            ← Task 8 (pre-flight)
Task 2, 5, 6, 7   ← Task 9 (summary)
```

## Implementation Notes

- **Shell safety is non-negotiable.** Every Bash command that touches file paths must use quoted variables. The SKILL.md must explicitly state this constraint with examples.
- **No source file modification.** The skill reads source files and writes new files alongside them. `rm`, `mv`, or in-place edits on source files are forbidden.
- **Graceful degradation.** If pandoc/pdftotext/python3 is missing, the skill reports the gap and continues with available tiers. A system with only pandoc still converts 10 formats.
- **Disk-mediated dispatch.** PDF structurer and digest agents use the shared dispatch convention (`skills/shared/dispatch-convention.md`). Dispatch files go to `/tmp/crucible-dispatch-<session-id>/`.
- **Idempotency.** Re-running `/distill` on the same file overwrites existing output. No backup or versioning.
