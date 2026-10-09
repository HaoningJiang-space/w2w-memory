# Matching-aware placement: registered minimal experiment

This experiment extends the existing work on `main`; it does not replace bank
service or slice-exposure results. No new branch is used.

## Claim and scope

For N compute and N memory reticles, let A[c,m] be the fixed fraction of every
compute's byte stream resident on memory m. Each row sums to one; no replication,
forwarding or migration. If every compute sustains 1 TB/s and every memory has
1 TB/s service, all column sums must also equal one. Thus A is doubly stochastic.
The Birkhoff–von Neumann decomposition expresses A as a convex combination of
perfect matchings supported by the physical adjacency graph. A unique perfect
matching forces that one layout under these assumptions. This is an application
of an existing theorem, not a new graph theorem.

Unequal resources, non-unit service floors, replicated data, forwarding and
unsaturated full load require a more general transportation model. Multiple
matchings alone do not prove useful pooling or bank-level implementability.

## Structural audit

- Collapse physical port overlaps into C–M adjacency.
- Find allowed edges using alternating directed strongly connected components.
- Independently force every edge and match the remaining N−1 nodes.
- Compute maximum edge-disjoint matching count through integral k-factor flow,
  then decompose that regular subgraph. Greedy removal is not used to claim a
  maximum. We do not count all perfect matchings (the permanent).
- Report allowed-edge count and affine dimension of the supported doubly
  stochastic polytope, |E_allowed|−2N+components, in addition to degree.

## Controlled placement family

Use the upstream H/plus templates, with 36C+36M inside a 300 mm circle. Each
reticle remains 844.8 mm²; all five port rectangles remain 0.4×8.25 mm. Each port
is provisioned 0.8 TB/s, each reticle 4 TB/s HB, each memory 1 TB/s service,
and each compute 4 TB/s controller. No area-based DRAM scaling is applied.

Enumerate horizontal center pitch {25.6,25.7,25.8,25.9,26.0} mm and alternating
column vertical stagger {0,8.25,16.5} mm, identically on both wafers. Validate
same-wafer non-overlap, circular containment, port containment, and repeated
templates. Reject invalid geometry and report why. Keep counts, shapes, port
areas and provisioning fixed. Usable link capacity scales with actual overlap.
This is a small packing-placement search, not an exhaustive relative-wafer or
shape search, nor a claim of new contoured geometry.

Rectangular Aligned/X/XY graphs are structural diagnostics. Their 858 mm² area
and four ports differ, so they are not an equal-cost performance comparison.
The fixed five-port allocation is also not an optimized home-only baseline:
its single home connection supplies only 0.8 TB/s. Report this explicitly.

## Matching/layout selection and evaluation

Candidates: home only; home + deterministic non-home perfect matching; home +
complete reciprocal pair-swap matching chosen by maximum cardinality then
short center distance; first two matchings from the maximum k-factor packing.
Home weights {0.2,0.35,0.5,0.65,0.8}; analogous weights for the packed pair.
Also include the capacity-balanced weight h0/(h0+h1), where hi is the minimum
C–M link capacity along matching i; this equalizes weakest-link solo ceilings.
Pairs use no workload statistics. All layouts are frozen after training.

Register train seeds 91000–91007, held-out seeds 92000–92019. Per seed: random
9/36, random 18/36, nearest-nine cluster on logical 6×6 indices, and nine highest
values of a Gaussian-smoothed random 6×6 field (sigma=1, reflect boundary).
The same logical active IDs are used for every placement. These synthetic
distributions do not represent measured application traces. No separate
hotspot claim is made without an address/bank access model.

Select highest training mean throughput among candidates certified to sustain
full-load common rate 1. This floor is a controlled experiment isolating the
matching hypothesis, not a permanent restriction on the research design space.
Also retain rejected candidates' full-load rate and the best full-load common
rate with unconstrained reticle byte distribution. Test selected layouts and
each feasible fixed 50/50 structural candidate, without test-time reselection.

The continuous service LP enforces fixed bytes per C–M pair, each memory's
1 TB/s, each controller's 4 TB/s, both endpoint ports, and every overlap edge.
Throughput optimizes sum rates with minimum 1 for each active compute; common
service is solved separately. Record rates, P5, residuals and common bandwidth.
No runtime LP in hardware is proposed; these are fluid service bounds.

Memory internally remains pooled at reticle level: the LP does not yet prove
which banks or LIO endpoints expose these bytes. Matching mixtures are data
fractions, not time multiplexing of hardware switch configurations. A later
bank/slice projection must preserve endpoint bandwidth and address semantics.

## Reproduction

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m unittest tests.test_matching_placement -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m w2w.experiments.run_matching_placement --output memory_results/matching/results.json
```

Primary references: [upstream H/plus geometry, §4.2](https://arxiv.org/html/2603.05266v1),
and [Goel, Kapralov and Khanna's matching/decomposition algorithm](https://arxiv.org/abs/0909.3346).
Novelty relative to other HB architectures is not established by this probe.
