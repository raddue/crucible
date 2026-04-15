#!/usr/bin/env python3
"""Minimal selection-eval runner.

Reads evals/evals.json, runs each prompt via `claude -p --output-format stream-json`,
inspects tool_use events to decide which skill was selected.

Detection: `Skill` tool_use → skill arg; `SlashCommand` with /build → "build";
`Task`/`Agent` → "raw-dispatch"; none → "no-selection".
Pass = selected skill matches expected_skill.
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

EVALS_JSON = Path(__file__).resolve().parent.parent / "evals" / "evals.json"


def project_root() -> str:
    for p in [Path.cwd(), *Path.cwd().parents]:
        if (p / ".claude").is_dir():
            return str(p)
    return str(Path.cwd())


def detect(stream_text: str) -> str:
    for line in stream_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") != "assistant":
            continue
        for item in ev.get("message", {}).get("content", []):
            if item.get("type") != "tool_use":
                continue
            name = item.get("name", "")
            inp = item.get("input", {}) or {}
            if name == "Skill":
                sk = inp.get("skill") or inp.get("skill_name") or ""
                if sk:
                    return sk
            if name == "SlashCommand":
                cmd = f"{inp.get('command', '')} {inp.get('args', '')}"
                if "/build" in cmd:
                    return "build"
                for tok in cmd.split():
                    if tok.startswith("/"):
                        return tok.lstrip("/")
            if name in ("Task", "Agent"):
                return "raw-dispatch"
    return "no-selection"


def run_one(prompt: str, timeout: int, root: str, model: str | None) -> tuple[str, str]:
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
           "--permission-mode", "bypassPermissions"]
    if model:
        cmd += ["--model", model]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              cwd=root, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return ("no-selection", "timeout")
    except FileNotFoundError:
        return ("no-selection", "claude-not-found")
    except Exception as e:  # noqa: BLE001
        return ("no-selection", f"spawn-error:{e}")
    return (detect(proc.stdout.decode("utf-8", errors="replace")), "")


def expected_first(entry: dict) -> str:
    exp = entry.get("expected_skill")
    return (exp[0] if exp else "") if isinstance(exp, list) else (exp or "")


def run_seed(entries, timeout, root, model, label):
    per, passed = [], 0
    for i, e in enumerate(entries, 1):
        exp = expected_first(e)
        t0 = time.time()
        sel, err = run_one(e["prompt"], timeout, root, model)
        dt = time.time() - t0
        ok = sel == exp
        passed += ok
        per.append({"id": e.get("id"), "expected": exp, "selected": sel,
                    "pass": ok, "elapsed_s": round(dt, 1), "error": err})
        print(f"  s{label} [{i:02d}/{len(entries)}] {e.get('id')}: exp={exp} got={sel} "
              f"{'PASS' if ok else 'FAIL'} ({dt:.0f}s){' ['+err+']' if err else ''}",
              file=sys.stderr, flush=True)
    return {"seed": label, "pass_count": passed, "total": len(entries),
            "pass_rate": passed / len(entries) if entries else 0.0,
            "per_prompt_results": per}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boundary", default=None)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--model", default=None)
    ap.add_argument("--evals", default=str(EVALS_JSON))
    a = ap.parse_args()

    data = json.loads(Path(a.evals).read_text())
    entries = data.get("evals", data) if isinstance(data, dict) else data
    if a.boundary:
        entries = [e for e in entries if e.get("boundary") == a.boundary]
    if not entries:
        print("No eval entries matched filter.", file=sys.stderr)
        sys.exit(1)

    root = project_root()
    print(f"Running {len(entries)} prompts x {a.seeds} seed(s), timeout={a.timeout}s",
          file=sys.stderr)

    runs = []
    for s in range(1, a.seeds + 1):
        label = s if a.seeds > 1 else a.seed
        print(f"--- seed {label} ---", file=sys.stderr)
        r = run_seed(entries, a.timeout, root, a.model, label)
        runs.append(r)
        print(f"seed {label}: {r['pass_count']}/{r['total']}", file=sys.stderr)

    counts = [r["pass_count"] for r in runs]
    median = statistics.median(counts) if counts else 0
    total = runs[0]["total"] if runs else 0
    gate = median >= 8 and total >= 10
    print(f"Median: {median}/{total} gate_pass={gate}", file=sys.stderr)
    print(json.dumps({"runs": runs, "median": median, "total": total, "gate_pass": gate},
                     indent=2))
    sys.exit(0 if gate else 1)


if __name__ == "__main__":
    main()
