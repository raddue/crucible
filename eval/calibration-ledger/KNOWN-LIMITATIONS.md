# Known Limitations — calibration-ledger Phase 1

## T-1 cross-platform validation

| Platform | Status | Notes |
|---|---|---|
| WSL2 `/mnt/` (9p NTFS) | PASS | Validated 2026-05-19; all 16 assertions green. |
| Linux ext4 | PASS | Validated 2026-05-19 from `/tmp/` on same WSL host (cwd reported as `ext2/ext3` family); all 16 assertions green. |
| macOS APFS | **DEFERRED** | See [issue #280](https://github.com/raddue/crucible/issues/280) (`blocker:v1.0.1`). User has Mac access via work laptop; validation will run before PR merge per the user's commitment (option 3 of the build skill's APFS-handling questions). |

## Action items
- Before merging the Phase 1 PR: user runs `python3 eval/calibration-ledger/test-concurrency-t1.py` on an APFS Mac and reports PASS/FAIL. If PASS, this file is deleted and PR body updated to `APFS=PASS`. If FAIL, the mkdir-lock + single-write() protocol is invalidated on APFS; redesign required.

## Why the carve-out exists
The mkdir-lock + holder-file + single-`write()` syscall protocol is the v1 architecture's load-bearing concurrency mechanism. The 16 KiB single-`write()` atomicity claim is filesystem-dependent (documented as holding on ext4, APFS, and 9p). T-1 is the test that defends that claim. Shipping without APFS validation means the claim is verified on two of three target filesystems; the third is tracked in #280 and will be validated before the PR is merged to main.
