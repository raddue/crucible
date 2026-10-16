# Generating evals from trajectory data

### Generating Evals from Trajectory Data

When creating or improving evals for a skill, check for trajectory data at
`~/.claude/projects/<hash>/memory/trajectories/`. If trajectory files exist
and contain entries for the target skill, offer to generate eval scenarios from
real usage patterns.

#### Reading Trajectory Data

1. Parse `failed_trajectories.jsonl` for entries where `skill` matches the target skill.
2. Also read `trajectory_samples.jsonl` for successful entries of the same skill.
3. If no trajectory data exists for this skill, skip this section and proceed
   with hand-crafted eval creation as normal.

#### Clustering Failure Patterns

Group failed trajectories by:
- `deviation_type` (over-engineering, under-scoping, wrong-assumption, etc.)
- `phases_reached` (failures that stop at design vs. failures that stop at execution)
- `error_recovery_events` (0 = no recovery attempted, 1+ = recovery attempted but
  insufficient)
- `prompt_summary` similarity (group similar task types)

Each cluster represents a category of failure that should be tested.

#### Generating Eval Prompts

For each failure cluster with 2+ entries:
1. Identify the common characteristics (task type, complexity level, failure point)
2. Write an eval prompt that reproduces those conditions WITHOUT using any
   specific content from the original trajectories. The prompt should test the
   *category* of task, not replay the specific instance.
3. Write expected_output describing what a successful handling looks like
4. Add expectations that specifically test the failure mode: if the cluster
   fails at error recovery, add an expectation about error handling. If it
   fails at the design phase, add expectations about design completeness.

#### Cross-Referencing with Successes

Compare each failure cluster against successful trajectories of similar task types:
- What did successful invocations do that failed ones did not?
- Were there more tool calls? Different phases reached? Lower error recovery counts?
- Use these differences to inform the expectations: test for the behaviors that
  distinguish success from failure.

#### Tagging Generated Evals

Add these fields to trajectory-generated eval entries in `evals.json`:

```json
{
  "id": "<next-id>",
  "prompt": "<generated prompt>",
  "expected_output": "<expected result>",
  "source": "trajectory",
  "trajectory_cluster": "<cluster description>",
  "failure_count": "<number of trajectories in the cluster>",
  "files": [],
  "expectations": []
}
```

The `source` and `trajectory_cluster` fields distinguish auto-generated evals
from hand-crafted ones. Present all generated evals to the user for review
before adding them to the eval suite — do not auto-add without approval.
