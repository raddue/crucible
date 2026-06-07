#!/usr/bin/env python3
"""Runtime receipt linter (Ledger Return Protocol). Tier-1 (v1 structural, ported
verbatim from eval/ledger-return-protocol/lint.py) + Tier-2 parts 1-2 (disk sha256 +
witness byte-range). stdlib-only, argparse-free. Exit 0=pass, 1=fail; bullets on stderr.

Usage:
  rcpt_verify.py [--tier1|--tier2] [--root DIR] [--strict] [FILE|-]
  rcpt_verify.py --selftest
  rcpt_verify.py --eval FILE.jsonl
"""
from __future__ import annotations
import json, re, sys, hashlib, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "eval/ledger-return-protocol"


class LintError(Exception):
    pass


def _usage_exit():
    sys.stderr.write(__doc__)
    return 2


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return _usage_exit()
    # dispatch stub — filled in later tasks
    return _usage_exit()


if __name__ == "__main__":
    sys.exit(main())
