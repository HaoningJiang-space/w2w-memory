# Wafer-scale Memory Fabric DSE

The research objective is to discover useful **geometry-constrained memory
fabrics**, not to certify only k=2, reciprocal or lossless designs. The earlier
`guaranteed_service_exchange` remains one interpretable reference family. This
mode broadens the graph and width variables while preserving source attribution,
train/test separation, and distinct static versus free-remapping results.

## Variables and objective

For each legal placement P, derive physical compute-to-port overlaps y(P).
The repeated memory template has binary bank-port edges x[b,p] and port data
widths q[p]. A route exists only if both y and x permit it. Service is constrained
by each bank, bank output, aggregation port, HB overlap, compute port and
controller. The same width vector is repeated on both wafer templates in this
first search; independently sized compute/memory ports remain unexplored.

Maximize average training served bandwidth for each resource-budget profile.
Compare service floors 0, 0.9, 1 TB/s. Floors 0.9/1 apply to every active client,
a stronger constraint than P5 alone; **floor 0 imposes no protection**. Report
P5, full-load loss, common completion and mean separately. The throughput-only
LP can have multiple optimal service allocations; its individual P5 values are
solver-selected, not a separate fairness optimum.

## Small open search

- Placements: aligned, X, XY, upstream H/plus, always 36C+36M.
- Masks: private, sparse, nonuniform degree (extra exposures for a bank subset),
  full crossbar. The bank subset is a design seed, not falsely labeled a measured
  set of hot banks. Rectangles have 4 ports, H/plus has 5. Record actual degrees.
- Two initial width vectors per placement, all summing to 32000 bits at 1 GHz
  (4 TB/s). Rectangular vectors include 4000/4000/12000/12000. H/plus vectors
  include home 8000 plus two 12000-bit directions. A zero-width port remains a
  physical region but provides no service.
- One local-search round per placement starts from the best <=64-edge,
  floor-0.9 training seed. Try four single-bank edge additions/removals and up to
  four 1000-bit bandwidth transfers. Masks are repeated across the wafer, and
  bank degrees may differ. Edge removal need not preserve home.
- Compare 64/160 connection budgets and 800/1000/1400 mm memory-side centerline
  wire budgets. Same width budget does not imply equal area, especially between
  rectangular and H/plus shapes; area and fan-in remain explicit.

This is a finite seed search plus a local improvement heuristic, **not a global
joint optimum**. Choices are taken across placement, graph, width and layout;
per-placement best results provide the fixed-placement ablation. The search
space and training seeds are registered before held-out evaluation.

## Static layout co-design

Architecture-only uses identical home bank proportions for every candidate,
including inaccessible-home failures. Offline co-design constructs a target
using training `P(memory-owner idle | requester active)`, then L1-projects it onto
full-load bandwidth and storage feasibility at a design rate 0.9 or 1.0.
The projection retains compute-bank byte proportions and every route resource.
This LP is a constructive approximation to the nonconvex joint layout/rate
problem; it is not claimed to maximize expected throughput globally. Balanced
peer fractions 1/8, 1/4 and 1/2 are additional candidates where applicable, for
both opposite direction pairs and the four-direction k=2 seed. Local graph/width
edits inherit all parent static layouts as candidates; an added edge must not
look worse merely because a good parent layout was discarded.

Layouts are frozen **continuous byte fractions**, representing arbitrarily fine
static striping. No replication or per-test movement. Unlike the integer-stripe
reference Gate, this broader DSE does not yet quantize the fractions into pages;
implementable address mapping is an open evaluation step. Every logical object
has the same bank proportions with uniform access within the object, so this
study does not establish a benefit from exposing real hot banks differently.

Each winning fabric is evaluated with fixed home, selected static layout and a
free-residency oracle using the same graph/widths. Missing fixed-home feasibility
is reported, not silently repaired. The oracle ignores stored bytes and migration
cost; it is a potential bound, **not a dynamic-remapping implementation**.

## Protocol and accounting

Training seeds 300–301; 25/50% active; uniform/clustered/correlated. Test seeds
4000–4005; 25/50/75/100%; those patterns plus object hotspot. Every architecture
receives identical active IDs. Spatial patterns use the H/plus coordinates.
Selection is saved before test solves. Template widths and frozen layout hashes
are recorded. No test-dependent architecture/layout choice.

The demand-limited fully pooled bound is `min(total demand,36 TB/s)` (controller
caps are already reflected in 4 TB/s active demand). Report:

- total resource gap = bound - served;
- fixed-residency gap = same-fabric free-residency oracle - served;
- graph/width gap = bound - same-fabric oracle.

These are relaxation gaps, not a physical partition of independently reusable
idle bytes. At full load there is no idle-resource denominator. Pooling gain
recovery ratios are only meaningful with a positive baseline-to-oracle gap.

Cost proxies and physical limitations from `docs/methods/GUARANTEED_EXCHANGE_METHOD.md`
apply. No placement signoff, synthesized area, energy or real workload claim.
Do not interpret structural opportunity or joint-search improvement as proof of
novelty versus SiloBreaker without its full text.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m unittest tests.test_memory_fabric_dse -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m w2w.experiments.run_memory_fabric_dse --output memory_results/memory_fabric_dse
```

## Preliminary-run audit and revised holdout

Commit 46ecc01 was evaluated with seeds 3000–3005. Its local mutations did not
inherit constructive parent layouts, weakening that comparison. The revised
run preserves those layouts and includes both opposite direction pairs and
four-direction seeds. Seeds 4000–4005 are registered as a fresh held-out set;
3000–3005 results remain diagnostic and are not reported as final validation.
The earlier raw run is retained at `memory_results/eex005_dse_46ecc01`.
