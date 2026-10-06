# Guaranteed-service reciprocal bank exposure: registered experiment

This mode is independent of `bank_sharing.py` and its published Gate. Maintain
only `main`; experiment IDs and commits, not additional branches, distinguish
stages. The user-supplied independent audit is a hypothesis/configuration source;
its unavailable ZIP/scripts have not been executed here.

## Design and constraints

Reuse the upstream H/plus primitives, with 36 matched compute/memory centers,
300 mm wafers, 844.8 mm² reticles, 36 home adjacencies and 55 reciprocal pairs.
Both masks and widths repeat on all reticles. Polygon/region checks establish
geometric compatibility only; bank centers are not a macro floorplan and pad
alignment/manufacturability are unverified. Boundary groups without partners
remain private, without periodic edges or memory-side forwarding.

Each memory provides 32 banks, 16 GiB and 1 TB/s. Each compute holds 128 logical
32 MiB objects and has a 4 TB/s controller. A logical object contains 256 unique
128 KiB stripes: no replication or runtime migration. All objects use the same
frozen bank proportions, and **accesses are assumed uniform within each object**.
Consequently object-level hotspot weights cancel; address skew inside objects
is outside this experiment. The stronger striping applies to every baseline.

Candidate bank masks retain home port 0 plus one sharing port (k=2). Balanced
sharing directions are (1,4), (2,3), or (1,2,3,4). The last has four potential
peers but still only TWO outputs per bank. Minimum-cost assignment allocates
32 bank centers into equal port groups, minimizing Manhattan distance. Candidate
peer-byte fractions are 1/8, 1/4 and 1/2. Unpaired boundary groups stay home.
Static byte conservation is enforced for every compute-bank pair:

`sum(route service to bank b for compute c) = fixed_share[c,b] * rate[c]`.

A full-load service LP must certify 1 TB/s for every compute before training.
Its flows restricted to any active subset remain feasible, providing a fluid
service certificate. The certificate does not establish queueing latency,
protocol fairness, or deadlock freedom in a physical implementation.

## Width and cost accounting

At 1 GHz, W parallel data bits provide W/8000 TB/s. Every bank-output edge is
256 bits (0.032 TB/s), capped additionally by its bank's 0.03125 TB/s service.
The LP constrains bank service, each bank output, each memory aggregation/arbiter
port, each HB overlap region, each compute receiving port and the controller.
Aggregation requires parallel lanes; a narrow many-to-one selector is not
credited with whole-memory bandwidth.

Home port width is 8000 bits. Each selected shared port sweeps 256, 1000, 2000,
4000, 8000 bits; configurations above 32000 total bits are excluded. All have
**the same maximum HB budget of 4 TB/s**, but provisioned widths differ and are
reported as cost, not claimed identical hardware. A locked diagnostic uses the
user probe's home 16000 + shared 8000 + 8000 bits, exactly 4 TB/s.

Report per-memory-reticle bank-port count, fan-in, centerline mm, wire-bit-mm,
selector bit-input proxy, configured FIFO bits (depth 2), and pipeline-register
proxy (one stage per 2 mm). These proxies are NOT synthesized area, power,
frequency, congestion, or proof that arbitration achieves the modeled rate.
Controller and HB service budgets remain explicit. Unmodeled logic-side routing
means no total-system physical-cost claim is possible.

## Frozen train/test protocol

Training seeds **200–203**, active fractions 25/50%, four patterns (uniform,
hotspot, clustered, spatially correlated). Test seeds **2000–2009**, fractions
25/50/75/100%, the same four pattern generators. All architectures receive the
same active IDs generated from the contoured coordinates. Spatial interpretation
for X/XY is therefore ID-matched, not separately redrawn physical clusters.

Enumerate the finite candidate family, reject infeasible full-load certificates,
then maximize average training service under each wire budget (784, 850, 950 mm)
and total port-width budget (8000, 12000, 16000, 32000 bits). Ties prefer less wire,
width, peer fraction, then ID. Save selection before solving held-out phases.
This is the best enumerated candidate, **not a global architecture optimum**.

Two synthetic two-phase activity cohorts have identical per-client activity 1/2
but opposite preferred sharing directions. Their purpose is to test whether
joint activity can change the chosen repeated template; they are not real traces
or an out-of-distribution validation claim.

Locked seeds 1000–1009 audit the supplied probe separately. The existing scenario
generator's SeedSequence and coordinate ordering govern the samples; do not
claim its sample mean must equal the unavailable independent script. Exact
uniform 9-of-36 expectations (1.327731 for two peers, 1.186211 for four) are
independent of random seeds and checked against the explicit half/half model.

## Baselines, oracles, and stopping conditions

Strengthened aligned private/full, X xor_1/full, XY star_0/full use the same
within-object home striping. Inaccessible mappings fail certification and remain
reported; continuous layout LPs at floors .8/.9/.95/.99/1 additionally maximize
non-home proportions rather than attributing geometry limitations to a heuristic.

Home-only on the same H/plus contour isolates the sharing mechanism. Fixed
half/half references and the original-width/cyclic-assignment probes isolate
static fraction, width and wire assignment. The trained design changes none of
these at test time. Each tested fabric also gets a free-residency oracle with
its exact widths and minimum-service constraint. A separate full-bank-crossbar
oracle uses the entire 4 TB/s HB budget and no fixed residency; contoured has
FIVE ports, so this oracle is k=5, not mislabeled k=4. It ignores stored-byte
placement/capacity and is an upper bound, not a deployable data mapping.

Report mean throughput, minimum/P5 service, separately optimized common
completion, worst sample, and fixed-data LP bottleneck rows. Never equate average
throughput gain with synchronous application acceleration. Report cost vectors
and budget-specific winners; a scalar cost weight is not a measured PPA model.
If gains require unaffordable widths/wires or fail the application's completion
objective, the Gate remains conditional or stops. No DRAM timing, trace pipeline,
runtime scheduler, SI, thermal, yield or PDN expansion in this Gate.

## Prior work and reproduction

- [Iff et al., §4.2](https://arxiv.org/html/2603.05266v1): H/plus contoured placement
  is reused, not proposed here.
- [H²EAL, §IV-B3](https://arxiv.org/html/2508.16653v2): within-page token interleaving
  across banks motivates a strong baseline, not a new contribution.
- [Flexible Queueing Architectures](https://arxiv.org/abs/1505.07648): dynamic
  task-server flexibility does not prove gains for mandatory fixed byte shares.
- [SiloBreaker publication record](https://fengbintu.github.io/publications/):
  resource-silo/sharing novelty is not claimed; full-text overlap remains open.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m unittest test_memory_model test_bank_sharing test_guaranteed_service_exchange -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python run_guaranteed_exchange.py --output memory_results/guaranteed_exchange
```
