# Sparse pooling: first construction probe

Protocol registered before remote performance measurements. This extends the
two-path model without changing old experiments or adding a Git branch.

## Question and distinct objects

Does the existing finite H/plus physical graph support degree-3/4 sharing, and
does a small family of realizable static matching mixtures improve service?

1. A **d-factor** has exactly d distinct edges at every C and M. Its uniform
   layout is A=1/d on those edges. Integral max-flow supplies either a regular
   subgraph and d disjoint perfect matchings or a min-cut infeasibility witness.
2. A **mixture of d matchings** can reuse edges. Then support degrees can be
   smaller than d and nonuniform. These are not d-factors.
3. A **complete local pool** is K_d,d with uniform fixed stripes. Disjoint such
   pools are globally sparse but locally fully connected. This is a specific
   geometry-relaxed construction, not a proven upper bound over all degree-d
   fixed-data graphs. No replication or migration is assumed.

For a focal active C in a uniformly sampled 9-of-36 set,

    Pr(K=k) = choose(d-1,k-1) choose(36-d,9-k) / choose(35,8)
    r(K) = min(d/K, 0.8*d, 4).

The expectation is 1.462857, 2.007395, 2.450726 for d=2,3,4. Verify this
construction against explicit service LPs for every nonempty local active set.
These values do not establish that arbitrary regular sparse graphs attain them.
The old free-data XY value near 2.47 is a different comparator. The aggregate
36-memory/9-controller bound here is 4; it is not the old 2.47.

A single 0.8-TB/s edge cannot supply the unit baseline. A degree-1 point at 1
requires a different interface allocation (e.g. aligned parallel HB regions),
and must not be plotted as though it retained this per-edge constraint.

## Physical feasibility first

Retain all 36 C and 36 M at pitch 25.6, including boundary nodes. Retain all
five 0.8-TB/s physical ports per reticle (4 total), memory service 1, controller
4. Check 2/3/4-factor max-flow and explicit cut capacity; enumerate K2,2/K3,3/K4,4.
Do not silently remove edges/nodes, add wraparound links, or treat independent
logical edges as additional physical ports.

Preliminary read-only construction checks found flow 72/72, 106/108, 126/144.
Thus global 3/4 factors are already ruled out; this is a result to reproduce,
not a solver-performance question. Max-flow integrality suffices, no ILP needed.

## Small feasible family, not a global synthesis claim

Start with the known home + reciprocal-pair matching cover. Add a third, then
fourth matching, allowing repeated edges. For eight design seeds 0–7, use a
linear assignment objective: first maximize new support edges, then minimize
the increase in squared multiplicity, then random tie-breaking. The factor
1000 dominates the total multiplicity term; total random cost is below 0.1.
Uniform matching weights are fixed at 1/3 or 1/4. Deduplicate identical layouts.
This tests a reproducible, limited design family; negative results are not an
optimality certificate for all static A on this physical graph.

All candidates must conserve bytes, have row/column sums 1, use actual paths,
and pass the explicit memory/edge/both-port/controller unit full-load audit.
Use the same reticle-level pooled-memory relaxation as previous experiments;
no repeated bank/LIO circuit implementation or PPA is claimed.

Train separately for random25/random50/cluster25/correlated25 on seeds
110000–110127, select once within each 3/4-term family, then freeze A. Re-synthesize
the old pair/3/4-cycle baseline using exactly this same training set. Pair is
the unique static pair cover. Test all four methods on new seeds 310000–311023
(1,024 per distribution). No test-dependent selection; archive every candidate
training score, selected layout and its hash. These numbers replace neither
the older 4,096-seed report nor its different training protocol.

## Correct service semantics and checks

For fixed A, f_cm=A_cm*r_c. Enforce unit active floor and maximize sum r. A
separate common-rate objective measures synchronous service. With d>2, do not
reuse the special formula requiring all competitors to be idle: it is not
valid for general pooling.

The new rate-only LP eliminates unique physical C–M flows algebraically, but
keeps every memory, edge and both endpoint port resource. Reject parallel C–M
paths; shared ports retain their combined load. Reconstruct resource loads
independently for every solved state. Cross-check throughput and common against
the existing explicit-flow LP at 16 registered test indices and full load for
each of 16 selected designs. Compare objective values rather than rate vectors,
because degree>2 sum-throughput solutions need not be unique. P5/minimum refer
to the returned optimum, not an additional max-min tie-break objective.

Unit tests precede the remote experiment: cut/decomposition witnesses, all
local block active subsets, nonuniform-mixture/explicit-flow equivalence and
shared-port rejection when full-load budget fails. Store clean source commit,
host, seeds, layout hashes, raw per-scenario means/common and paired intervals.

## Interpretation boundary

More support can increase solo bandwidth but also creates more mandatory byte
sources and competitors. Degree alone need not improve fixed-data service.
The ideal-block gap cannot yet be credited entirely to placement: richer
static ratios, task-to-reticle mapping and alternative feasible mixtures remain
controls. In particular arbitrary pair grouping can be reproduced by relabeling
tasks onto the existing pair slots if task placement is unconstrained. Relabeling
cannot create a missing K3,3 physical block.

The reported three/four-term families force equal weights and extra exposure.
An optimum under an **at-most-d** connectivity budget can always retain a
two-path design; a regression in the forced family does not imply that adding
an optional hardware budget reduces the best attainable performance.
