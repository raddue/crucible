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

## Phase-1b pilot calibration revision (2026-06-16)
The neutral-proxy calibration pilot put paginate below the 40–70% catch band
(0.25), because two seeded bugs were not detectable from the blind producer copy:
their intended behavior lived only in stripped docstrings, not in code. The bug
*identities and descriptions are unchanged*; only their code seam was repaired so
the intended behavior survives the producer strip:
- **pg-b2** (response-envelope shape): added `src/paginate/client.py`, the
  downstream consumer that reads the documented envelope
  (`resp["data"]` / `resp["paging"]["next_cursor"]`), wired via `App.records`. The
  consumer is the strip-surviving signal of the intended shape that previously
  existed only in a docstring. `App.records` / `client.py` exist purely as this
  strip-surviving consumer-seam SIGNAL for pg-b2 (a downstream consumer that must
  be reconciled with the flat envelope `routes` returns); they are not otherwise
  exercised by the package's default path.
- **pg-b6** (default page size): relocated from `Paginator.page` (dead on the
  public request path — `normalize_limit` resolved the default first) to
  `validate.normalize_limit`, so the wrong default is observable through the public
  API against the strip-surviving `DEFAULT_PAGE_SIZE` constant. Its fix patch and
  exemplar were regenerated accordingly; behavioral independence re-verified.
