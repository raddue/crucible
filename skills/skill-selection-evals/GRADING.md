# Skill-Selection Eval Grading

## Running the Evals

Present each eval's `prompt` to the agent in a fresh conversation. Observe which skill the agent selects (invokes or announces it will use). Record the selected skill.

For cascade evals, record the full sequence of skills invoked.

## Grading Criteria

### Pass
- **Direct/Negative/Context-dependent**: Agent selects exactly the `expected_skill`.
- **Cascade**: Agent selects all skills in `expected_skill` in the correct order.

### Partial
- **Direct/Negative/Context-dependent**: Agent selects the correct skill alongside unnecessary additional skills, or selects a related skill that partially addresses the prompt.
- **Cascade**: Agent selects all correct skills but in wrong order, or omits one skill from the sequence.

### Fail
- **Direct/Negative/Context-dependent**: Agent selects a skill from `common_mistakes` or an unrelated skill. Agent does not invoke any skill.
- **Cascade**: Agent selects fewer than half the correct skills, or invokes them in fundamentally wrong order (e.g., build before design).

## Baseline Measurement Protocol

1. Run all evals against the current getting-started routing table and SKILL.md trigger descriptions without any modifications.
2. Record grade (Pass/Partial/Fail) for each eval.
3. Compute:
   - **Overall accuracy**: Pass count / total evals
   - **Per-boundary accuracy**: Pass count / evals in boundary
   - **Per-dimension accuracy**: Pass count / evals in dimension
4. Store results in `evals/baseline-results.json` with timestamp.

## Integration with Eval Summary

Selection eval results are reported alongside execution eval metrics:

| Metric | Value |
|--------|-------|
| Execution evals (with skill) | 96% |
| Execution evals (without skill) | 67% |
| Execution delta | +29% |
| **Selection accuracy** | *baseline TBD* |
| **Selection accuracy by boundary** | *baseline TBD* |

The selection accuracy metric answers: "When the agent receives a prompt, how often does it route to the correct skill?" This complements the execution delta which answers: "Once the correct skill is invoked, how much better is the output?"

## Interpreting Results

- **Low selection accuracy on a boundary** indicates the disambiguation guidance for those skills needs improvement (SKILL.md triggers, getting-started routing table).
- **Context-dependent failures** indicate the agent relies on verb matching rather than situational analysis.
- **Cascade failures** indicate the agent does not maintain pipeline discipline for multi-step workflows.
- **Negative selection failures** indicate trigger descriptions are too broad (matching prompts they should not).
