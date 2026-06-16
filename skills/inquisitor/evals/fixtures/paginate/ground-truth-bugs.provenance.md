# Ground-truth provenance — paginate

## Blind GT authoring
The bug list (bug_id, desc, fix_patch) for this seeded repo was authored from the
committed source tree plus the per-bug fix patches and the behavioral exemplar
tests only — i.e. from the observable wrong-vs-correct behavior of each seam. The
author was blind to the eval's lensed dimension taxonomy and to the arm/treatment
names; no taxonomy or treatment string was consulted while writing the
descriptions.

Blind input: skills/inquisitor/evals/fixtures/paginate/{src,fixes,exemplars}.

## Off-axis tagging (post-blind, disjoint role)
The off_axis flags were applied in a separate pass that ran AFTER the blind GT
authoring above was sealed, by a role disjoint from the GT author and from every
arm/exemplar test-authoring role. off_axis:true marks a defect that lies outside
the lensed dimension taxonomy (so the bare, un-lensed arms are credited fairly for
catching it); off_axis:false marks an on-taxonomy seam defect.

## Independence
All seeded bugs in this repo are pairwise behaviorally independent (verified by
scripts/check_fixture_independence.py); no interacting_sets are registered.
