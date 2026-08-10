#!/usr/bin/env python3
"""#474 S10 — corpus re-verification through the REAL linter, pre-fix vs post-fix.

Runs every recovered `rcpt-*-asreturned.txt` receipt through `rcpt_verify`'s own
functions — `witness_art_name`, `resolve_base`, `tier2_artifacts`, `tier2_witness` —
and reports every disposition flip between a baseline copy of the linter and this
working tree's. It replaces the interim `fix-8-measure.sh` probe, which had its own
resolver and its own `re.search` and therefore measured *pattern vs. body*, not
*receipt through the linter*: a probe that cannot fail reports the same answer whether
the fix is present, absent or broken.

Two things this does that the interim probe did not:

  (a) column (B) comes from `witness_art_name(witness, cited, verdict)`, the shipped
      function. The interim script derived the payload artifact+range for EVERY ranged
      grep receipt regardless of verdict, so it printed "body moves? YES" for the rows
      whose FAIL leg exits at `derive_art_name → None` — three phantom moves, forever.

  (b) each receipt runs TWICE: as returned, and as a synthetic PASS-leg variant with
      ONLY the VERDICT token flipped. No as-returned receipt carrying the mandated
      `pattern=`+`match` shape reaches the PASS leg (the one that does is a FAIL), so
      without the synthetic the `--strict` path-shaped flip class is invisible.

NOT a CI gate: the corpus is machine-local and gitignored. The committed, gated
regression surface for these shapes is `tier2-fixtures/manifest.jsonl` rows j-n plus
`scripts/test_rcpt_verify.py`; this is the instrument that measured them.

Usage:
  measure_474_corpus.py --corpus DIR --root DIR [--baseline OLD_rcpt_verify.py] [--strict]
"""
from __future__ import annotations
import importlib.util
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent


def load(path):
    spec = importlib.util.spec_from_file_location(f"rv_{abs(hash(str(path)))}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def disposition(rv, text, root, strict):
    """Run one receipt through Tier-1 + Tier-2 exactly as `--tier2` does.
    Returns (verdict_label, message_or_notes)."""
    try:
        verdict = rv.lint_receipt(text)
        sections = rv.parse_receipt(text)
        artifacts = rv.parse_artifacts(sections["ARTIFACTS"])
        trace = rv.parse_trace(sections["TRACE"])
        witness = rv.parse_witness(sections["WITNESS"])
        notes = rv.tier2_artifacts(artifacts, trace, root, strict)
        if verdict in {"PASS", "FAIL"}:
            notes = notes + rv.tier2_witness(witness, trace, root, strict, verdict)
        return "clean", "; ".join(notes)
    except rv.LintError as e:
        return "BLOCKED", str(e)


def body_source(rv, text, verdict_override=None):
    """Where the verified body comes from, via the shipped witness_art_name."""
    try:
        sections = rv.parse_receipt(text)
        trace = rv.parse_trace(sections["TRACE"])
        witness = rv.parse_witness(sections["WITNESS"])
        verdict = verdict_override or rv.lint_receipt(text)
        if not witness["ran"].startswith("TRACE#"):
            return "(not TRACE-cited)"
        idx = rv._trace_idx(witness["ran"])
        if not 1 <= idx <= len(trace):
            return "(ran= does not resolve)"
        art, from_payload = rv.witness_art_name(witness, trace[idx - 1], verdict)
        return f"{art} [{'payload' if from_payload else 'derive_art_name'}]"
    except Exception as e:                      # a probe must never mask a receipt
        return f"(unavailable: {type(e).__name__})"


def pass_leg_synthetic(text):
    """Only the VERDICT token flipped — findings body, WITNESS, pattern, ARTIFACTS and
    TRACE stay real and unmodified. Returns None when the receipt is already PASS."""
    m = re.search(r"^VERDICT  (FAIL|BLOCKED)  ", text, re.M)
    if not m:
        return None
    return text[:m.start(1)] + "PASS" + text[m.end(1):]


def main(argv):
    args = dict(corpus=None, root=None, baseline=None, strict=False)
    it = iter(argv)
    for a in it:
        if a == "--strict":
            args["strict"] = True
        elif a.startswith("--") and a[2:] in args:
            args[a[2:]] = next(it)
        else:
            sys.stderr.write(f"unknown argument {a!r}\n{__doc__}")
            return 2
    if not args["corpus"] or not args["root"]:
        sys.stderr.write(__doc__)
        return 2

    corpus = sorted(pathlib.Path(args["corpus"]).glob("rcpt-*-asreturned.txt"),
                    key=lambda p: int(re.search(r"rcpt-(\d+)", p.name).group(1)))
    if not corpus:
        sys.stderr.write(f"no rcpt-*-asreturned.txt under {args['corpus']}\n")
        return 1
    root = pathlib.Path(args["root"])
    new = load(HERE / "rcpt_verify.py")
    old = load(pathlib.Path(args["baseline"])) if args["baseline"] else None

    print(f"corpus: {args['corpus']}  ({len(corpus)} receipts)")
    print(f"root:   {root}   strict={args['strict']}")
    print(f"baseline: {args['baseline'] or '(none — post-fix dispositions only)'}\n")

    flips = []
    for path in corpus:
        text = path.read_text()
        legs = [("as-returned", text)]
        syn = pass_leg_synthetic(text)
        if syn is not None:
            legs.append(("PASS-synthetic", syn))
        for leg, body in legs:
            new_disp, new_msg = disposition(new, body, root, args["strict"])
            src = body_source(new, body)
            if old is not None:
                old_disp, old_msg = disposition(old, body, root, args["strict"])
                flipped = (old_disp != new_disp) or (old_msg != new_msg)
                mark = "FLIP" if flipped else "    "
                print(f"{mark} {path.stem:26s} {leg:15s} {old_disp:8s} → {new_disp:8s}  body={src}")
                if flipped:
                    flips.append((path.stem, leg, old_disp, new_disp, old_msg, new_msg))
            else:
                print(f"     {path.stem:26s} {leg:15s} {new_disp:8s}  body={src}")

    if old is not None:
        print(f"\n── {len(flips)} flip(s) ─────────────────────────────────────────────")
        for stem, leg, od, nd, om, nm in flips:
            print(f"\n{stem} [{leg}]  {od} → {nd}")
            print(f"  pre : {om or '(silent)'}")
            print(f"  post: {nm or '(silent)'}")
        print("\nEvery flip must be pre-declared in the plan's §4 with its guard AND its "
              "direction. A fourth flip class blocks merge until analysed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
