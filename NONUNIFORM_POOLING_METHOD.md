# Nonuniform static pooling: registered search and validation protocol

Question: can jointly changing support and static byte fractions retain sparse
random-demand gains while avoiding the regressions from forced equal-weight
three/four-matching mixtures? Keep the existing H/plus geometry, all 36 C/M,
146 physical edges, memory 1, five ports × 0.8, controller 4 and unit full-load
service. No migration, replication, forwarding or runtime layout selection.

## Feasible family and construction

A is a fixed doubly stochastic 36×36 matrix on real C–M edges. Each C/M has at
most four positive entries; total support at most 126 (the previous largest
four-term candidate). Positive entries are multiples of 1/60, with physical
capacity limit A_cm≤0.8. This is a registered finite *reticle-level* fraction
grid, not a claim that 60 independently serviceable DRAM slices exist.

On a legal alternating cycle containing 2/3/4 compute, add delta on one matching
and subtract delta on the other. Every row and column is unchanged. Reject
negative fractions, unphysical edges, degree/count excess and full-load resource
overcommit. Do not require cycles to partition the wafer: here they are local
layout updates, not disjoint final sharing components or runtime routing loops.

Current geometry has unique edges and one edge per physical port; the proposal
generator explicitly checks this contract. The evaluation model retains all
port resources. Future shared-port geometries require broader construction
constraints, not free independent edge capacities.

## Search and ablation

Baseline catalog: existing pair; trained pair/3/4-compute configuration cover;
the same seven three-term and five four-term candidates from sparse_pooling.py.
Normalize their numerical fractions onto the exact 1/60 grid. The equal-weight
and original cycle constructions are retained as fallback candidates.

Choose the best training baseline as the search start, then:

1. Ratio-only: preserve its exact positive support, adjust fractions.
2. Joint: start from the ratio-only result and allow support addition/removal.

Each stage uses at most four rounds. Enumerate both directions of all legal
alternating cycles of size 2–4, with step sizes min(5,bound), min(10,bound), bound
in 1/60 units. Here bound is the largest nonnegative, edge-capacity-feasible
step; degree/count constraints are checked after constructing the proposal.

Evaluate the current service LP and its dual multipliers. For a unique path,
the local sensitivity of mean service to A_cm is rate_c times the sum of
memory, edge and both-port inequality marginals (SciPy minimization convention,
objective is minus mean service). Use this only to rank moves: at degenerate
LP optima it need not be a unique derivative or a valid global gain bound.

Per round, evaluate the top eight sensitivity proposals plus four uniformly
sampled remaining proposals using actual service LPs on the entire training
set. Accept only a measured improvement >1e-7; stop if none improves. Fixed
search seeds are 700/701. Cache repeated layouts. This is a bounded heuristic,
not a global optimization certificate, and stopping is not local optimality
over every feasible circulation. There is no new runtime scheduler.

## Data isolation and objectives

Train seeds 410000–410255: synthesize the cycle baseline, evaluate old mixture
candidates, guide all search moves. Validation seeds 420000–420255: select a
single frozen design from the baseline pool, the baseline+ratio trajectory,
and the baseline+ratio+joint trajectory respectively. Do not use validation
to generate or accept moves. Stable ties keep the earlier fallback candidate.

All four demand distributions have their designs frozen before test activity
is generated. Test seeds 510000–511023 (1,024 each) are used only for reporting.
Each distribution gets its own offline layout, not one universal layout.

Report pair, cycle, validation-selected equal3/equal4, selected baseline,
ratio-only selection and joint selection on identical test sets. Main method
comparison is against **selected baseline**, not an intentionally weaker pair.
Selection guarantees nondecreasing validation score because fallback candidates
are included, but provides no samplewise or expected-test dominance guarantee.

Maximize per-scenario mean service subject to every active C≥1; separately
compute common rate. Record full-load feasibility, minimum/P5 of the returned
LP optimum, worst scenario, regression frequency, paired mean-difference CIs,
support/degree counts, all fractions, accepted moves and layout hashes.
No additional fairness tie-break is applied to nonunique throughput optima.

## Correctness before performance

- All proposed moves from both a pair and a four-term seed are checked for byte
  conservation, support budgets, physical feasibility and full-load service.
- Verify sensitivity sign and scale against a differentiable asymmetric two-C
  finite-difference example; do not claim that this resolves degeneracies.
- Independently compare sampled new fractions/supports against ReticleService,
  including common and sum objectives. Reuse prior factor/pooling tests.
- Every evaluated candidate passes full-load primal audit. Every solved state
  is checked against the full resource matrix, active floor and controller.
- Every reported test state also reconstructs resources from physical edges
  through primal_audit; check explicit flow LP at eight fixed test indices and
  full load for every method/distribution. Compare objective, not rate vectors.
- After downloading results, reconstruct integer layouts, replay accepted moves,
  verify hashes and recompute independent explicit-flow samples.

## Costs and interpretation

The support cap controls a logical connectivity proxy. It does not equal a
repeated bank template, equal mux area, wirelength, energy or interface width.
HB budget is unchanged, but new bank exposure circuitry remains unimplemented.
Any gain is fixed-data fluid service, not application latency or PPA.

For fixed A evaluation is LP. The old configuration baseline uses an ILP.
The new outer search is discrete circulation enumeration with LP evaluation,
not a purported linearization of the joint bilinear A_cm*r_c problem.

All code is committed and pushed before the eex005 experiment; results record
the clean source commit. Maintain the existing single main branch.

## Prospective mixed-distribution control

After completing the separately trained experiment, add a distinct control for
the stronger question: can **one frozen layout** serve all four distributions?
The search algorithm, budgets, steps, trial counts and seeds 700/701 are unchanged.
Use `--mixed`: 64 seeds 430000–430063 × four distributions give 256 equally
weighted training scenarios; 64 seeds 440000–440063 × four give 256 validation
scenarios. Select one baseline, one ratio and one joint layout on this mixture.
All four test profiles use the same corresponding layout/hash, with brand-new
test seeds 610000–611023 (1,024 per profile). Do not reuse the now-observed
510000-series tests for this new design. Report per-profile outcomes and the
equal-weight aggregate; do not tune the mixture weights after testing.

This added control is not a rerun that changes the first experiment's result.
Its training question and test set are distinct. It is needed because switching
between four distribution-specific frozen designs does not demonstrate that a
single memory fabric simultaneously avoids their respective regressions.
