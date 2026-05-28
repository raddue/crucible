# smoke-no-mock fixture

**Purpose:** verify the build skill's Mock Dispatch Mode (added in Task 2) is a true no-op when `CRUCIBLE_BUILD_EVAL_MOCK_DIR` is unset. This fixture genuinely runs build with real subagent dispatches, against a trivial single-file task. If it fails, Task 2's SKILL.md edit broke production behavior and must be rolled back before any other fixture work proceeds.

**Why it matters:** Task 2 is the highest-risk task in the #304 plan because it modifies the build orchestrator that runs every feature development session. Mocked fixtures (b1-b4) cannot prove that the *unmocked* path still works — by construction, they never exercise it. The smoke fixture is the only verification that production behavior is preserved.

**Usage:**

```sh
# Stage a workdir (no env vars in the returned dict)
python -m skills.build.evals.run_evals stage --fixture smoke-no-mock

# In a fresh shell with HOME set to the returned workdir/.home:
cd <workdir>
export HOME=<workdir>/.home
/build "Add a function add(a, b) to src/math.py that returns a + b."

# After build completes:
python -m skills.build.evals.run_evals score --fixture smoke-no-mock --build-output <workdir>
```

PASS requires both expectations: `src/math.py` exists and a callable `add` symbol is defined in it.

**Wall-clock cost:** ~10-30 minutes for the build run itself (full pipeline against a trivial task, real subagent dispatches). Run k=1 — replicates are not justified at this cost for a no-op-preservation check.
