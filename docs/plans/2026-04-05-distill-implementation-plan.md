---
ticket: "#111"
title: "Distill Skill — Implementation Plan"
date: "2026-04-05"
source: "spec"
---

# Distill Skill — Implementation Plan

## Task Overview

8 tasks across 3 waves. Wave 1 is the skill skeleton + Tier 1 (pandoc). Wave 2 adds Tier 2 (PDF) + Tier 3 (Python venv). Wave 3 adds the digest pass + pre-flight checks + integration.

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

### Task 3: Implement unsupported format handling

**Files:** `skills/distill/SKILL.md` (unsupported format section)
**Complexity:** Low
**Dependencies:** Task 1

Add the unsupported format guidance table. When a file's extension matches an unsupported format, output the specific conversion guidance (e.g., ".xls → export as .xlsx from Excel/LibreOffice"). Continue processing remaining files.

## Wave 2: Tier 2 + Tier 3

### Task 4: Implement Tier 2 PDF conversion

**Files:** `skills/distill/SKILL.md` (PDF section), `skills/distill/pdf-structurer-prompt.md`
**Complexity:** High
**Dependencies:** Task 1

Two-step PDF conversion:
1. Run `pdftotext -layout` to extract text
2. Dispatch a Sonnet structuring agent to recover headings, lists, tables from the layout text

Create `pdf-structurer-prompt.md` dispatch template:
- Input: raw pdftotext output
- Instructions: identify headings (by capitalization, spacing, font-size-implied patterns), recover list structure, identify table boundaries, detect code blocks
- Output: clean Markdown with recovered structure
- Add `<!-- DISPATCH: disk-mediated -->` header per dispatch convention

Include scanned PDF detection: if pdftotext output averages < 50 chars/page, report as likely scanned.

### Task 5: Implement Tier 3 Python venv conversion

**Files:** `skills/distill/SKILL.md` (Tier 3 section), `skills/distill/convert_pptx.py`, `skills/distill/convert_xlsx.py`
**Complexity:** Medium
**Dependencies:** Task 1

Implement venv management:
- Check for existing venv at `/tmp/crucible-distill-venv/`
- Create if missing: `python3 -m venv /tmp/crucible-distill-venv/`
- Install pinned deps: `python-pptx==1.0.2 openpyxl==3.1.5`

Create conversion scripts:
- `convert_pptx.py`: Read pptx, output slide-structured Markdown (slide title, content, speaker notes per slide, separated by `---`)
- `convert_xlsx.py`: Read xlsx, output one CSV per sheet. Implement formula-cell warning (>30% formula cells) and sheet count guard (max 20 sheets).

Both scripts accept input/output paths via command-line arguments (not env vars — Python argparse is safe). Scripts validate inputs and return non-zero on failure.

## Wave 3: Digest + Pre-Flight + Integration

### Task 6: Implement digest pass

**Files:** `skills/distill/SKILL.md` (digest section), `skills/distill/digest-prompt.md`
**Complexity:** High
**Dependencies:** Tasks 2, 4, 5

Create `digest-prompt.md` dispatch template:
- Input: full converted `.md` content
- Target: 20-30% of input word count
- Instructions per design doc section 4 (preserve structure, key data, eliminate redundancy)
- Add `<!-- DISPATCH: disk-mediated -->` header

Implement digest orchestration in SKILL.md:
- Word count check (skip files ≤500 words)
- Dispatch Sonnet digest agent
- Verify output is within 20-30% target (15-35% acceptable range)
- One retry if out of range (stricter or looser instructions)
- Large file chunking: if input >50K words, chunk by heading boundaries, digest chunks independently

### Task 7: Implement pre-flight checks

**Files:** `skills/distill/SKILL.md` (pre-flight section)
**Complexity:** Medium
**Dependencies:** Task 1

Implement three pre-flight checks:
1. **Zip bomb detection** (docx/pptx/xlsx): `unzip -l` to check uncompressed size. Abort if >500MB.
2. **PDF attachment detection**: `pdfdetach -list` to check for embedded files. Warn but continue.
3. **Encoding validation**: Post-conversion UTF-8 check. Attempt re-encoding on failure.

Pre-flight runs before conversion for each file. Failures are per-file (don't halt the batch).

### Task 8: Implement conversion summary and token metrics

**Files:** `skills/distill/SKILL.md` (summary section)
**Complexity:** Low
**Dependencies:** Tasks 2, 4, 5, 6

After all conversions complete, output a summary table:

```
## Distill Summary

| File | Format | Tier | Converted | Digest | Token Savings |
|---|---|---|---|---|---|
| report.pdf | PDF | 2 | report.md (4,200 words) | report.digest.md (1,100 words) | ~74% |
| data.xlsx | Excel | 3 | 3 sheets → CSV | N/A | N/A |

**Total:** 2 files converted, 1 digest produced, ~74% token savings on digestible content.
```

Token savings = `1 - (digest words / original converted words)`. Use word count as a proxy for token count (close enough for reporting).

## Dependency Graph

```
Task 1 (skeleton) ← Task 2 (Tier 1)
                  ← Task 3 (unsupported)
                  ← Task 4 (Tier 2)
                  ← Task 5 (Tier 3)
Task 2,4,5        ← Task 6 (digest)
Task 1            ← Task 7 (pre-flight)
Task 2,4,5,6      ← Task 8 (summary)
```

## Implementation Notes

- **Shell safety is non-negotiable.** Every Bash command that touches file paths must use quoted variables. The SKILL.md must explicitly state this constraint with examples.
- **No source file modification.** The skill reads source files and writes new files alongside them. `rm`, `mv`, or in-place edits on source files are forbidden.
- **Graceful degradation.** If pandoc/pdftotext/python3 is missing, the skill reports the gap and continues with available tiers. A system with only pandoc still converts 10 formats.
- **Disk-mediated dispatch.** PDF structurer and digest agents use the shared dispatch convention. Dispatch files go to `/tmp/crucible-dispatch-<session-id>/`.
