# Physical memory-access graph: bounded-sharing Gate

## Locked research boundary

Question: how do repeated DRAM/compute templates and relative WoW placement
constrain the useful bank-to-HB sharing fabric under bounded interface cost?
The design object is the composition of geometry, bank-interface connectivity,
and static data residency. Geometric degree is not memory-resource flexibility.

We do not claim novelty for HB DRAM, resource silos, bank pooling, workload
imbalance, or placement-derived wafer networks. Scheduling, DRAM timing, SI,
thermal, yield, PDN, protocols and fabrication validation are outside this Gate.

## Architecture and resource contract

36 compute and 36 memory reticles occupy a matched 6x6 rectangle inside a
300 mm circular wafer; this is not maximum-utilization circular packing.
Each 26x33 mm memory template has 32 banks (4 columns, 8 rows), 16 GiB total
storage and 1 TB/s aggregate bank service. Each bank contributes 1/32 TB/s.
Four quadrant HB regions provide 4 TB/s per-reticle total HB budget. Every
compute has the same 4 TB/s aggregate controller limit. Aligned, X half-shift,
and XY half-shift use the same compute IDs, resources and request scenarios.

The proposed circuit location is **memory-side digital bank-output selection
and arbitration before HB**, repeated unchanged on all memory reticles.
It is neither a logic-side crossbar nor free RDL fanout. No memory reticle
forwards traffic to another. This is a functional bandwidth model: no circuit
synthesis or DRAM-process feasibility, timing, energy, arbitration-delay or
read/write turnaround claim is made.

Each bank retains its quadrant's private port and connects to exactly k of
four ports. k=1,2,4 gives 32,64,128 bank-port connections per reticle. **k=4 is
full bank-to-port connectivity**, so only k=2 supports a sparse-fabric claim.
k=2 candidates include XOR pairs, stars, spatial cycles, chain, nearest-region,
and balanced mixed masks. These are a declared finite candidate family, not a
global optimum or proven expanders. Equal degree fixes edge count, not wire or
mux cost: port fan-in, Manhattan wire length, extra wire length and a 256-bit
wire-length proxy are also reported. The 256-bit width is illustrative.

## Static residency and service semantics

Every compute owns 128 unique 32 MiB logical chunks, 4 GiB total; all 144 GiB
of data is placed once, with no replication, migration or capacity overflow.
These are coarse address-layout units, not physical DRAM or OS page sizes.
The installed capacity is 576 GiB. No test phase repairs an inaccessible page.

* `home_striped`: client c's data striped over memory c's 32 banks. The same
  physical layout is used for every placement and k.
* `static_interleaved`: deterministic geometry-aware striping generated once
  on full bank-port connectivity for each placement, then frozen across k.
  It sees no demand observations. It is not an architecture-independent hash:
  comparisons across placements jointly change this conventional mapping.
* `static_train_greedy`: offline selection among training-load greedy,
  mask-aware striping, geometry-aware striping and home striping. Each mask
  receives a layout selected using training only, then both are frozen. This
  is best-of-heuristics, not a globally optimal static placement. A greedy
  capacity failure is recorded and that heuristic skipped; it is not a proof
  that the hardware mask is infeasible.
* `oracle`: free-bank-service relaxation that ignores data residency. It is
  an upper bound, not a demonstrated executable per-phase data placement.

The fixed-data LP maximizes sum of completed-stream rates. For every client,
bank flow must equal that client's rate times its fixed requested-byte share.
If any positive-share bank is unreachable the client's rate is zero. A second
LP maximizes a common served fraction alpha, with rate_c=alpha*demand_c.
This captures fairness/common fluid completion, not cycle-level latency.
P5 from one sum-throughput optimum is potentially degenerate; common-rate P5
is also reported. All flows obey bank, HB and controller service limits.

## Selection, held-out scenarios and diagnostics

Training seeds 0,1 use 25%,50% activity; test seeds 100--109 use
25%,50%,75%,100%. Four synthetic distributions are uniform random activity,
hotspot (80% of bytes on the first 16 logical chunks), contiguous clustered
activity, and spatially correlated activity. Active clients request 4 TB/s.
Rounding gives 9,18,27,36 active clients on the full wafer. These synthetic
phases test a mechanism; they do not establish a real workload's imbalance.

For each placement, mapping mode and k, select the repeated mask by mean
training throughput; ties prefer less extra wire. Offline mapping selection
uses those same training scenarios. No held-out score selects hardware or
mapping. Search scores and every layout hash are saved. Main suite: 36 designs
times 160 scenarios. Boundary diagnostics add 12 cases per design (uniform,
25% and 100%, three held-out seeds), for 6,192 records and two service LPs per
record, plus training LPs and max-flow certificates.

The boundary diagnostics retain the finite-wafer mask and data layout:

* finite: original 36-client geometry;
* interior-active: restrict demand to the common 25 clients with four matched
  XY ports, retaining all 36 memory reservoirs and all stored data; 25% rounds
  to six active clients, so this is not a same-active-count comparison;
* periodic reference: mathematical 6x6 torus reconnects missing boundary ports.
  It is not a manufacturing proposal or an infinite-size scaling experiment.

## Structural bound and stopping rule

For the oracle, source->compute->memory-port->bank->sink max flow equals the
LP optimum. Each case stores an exact min-cut capacity, its resource terms,
the deficient source-side compute subset, neighbor expansion and stranded
bandwidth relative to min(total demand,36 TB/s). This cut is an upper bound
for fixed residency, not a complete explanation of its additional data-mix
bottlenecks. The old 22 XY oracle cases are re-evaluated by max-flow and must
match the first Gate's LP results, explaining the original 2.467/1.889/1.828.

Proceed only if k=2 retains meaningful benefit with fixed/static residency,
captures a substantial fraction of the full-interface benefit, and placement
changes the useful fabric. Aligned direct-only geometry cannot share another
reticle's memory, even with k=4. Thus beating aligned is partly structural;
it does not establish superiority over a budget-matched forwarding NoC.
Different winning masks are evidence of coupling, not proof of a global
joint-synthesis advantage. k=4 improvements alone do not pass the sparse Gate.

## Run

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m unittest tests.test_bank_sharing tests.test_memory_model -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m w2w.experiments.run_bank_gate --output memory_results/eex005_bounded_gate --seeds 10
.venv/bin/python -m w2w.visualization.plot_bank_gate memory_results/eex005_bounded_gate
```

The default legacy input is `memory_results/eex005_gate/memory.json`; pass
`--legacy` if archived elsewhere. Raw artifacts include provenance, templates,
layouts, hashes, candidate training scores, cuts, service results and figures.

## Exact coverage simplification for this parameter regime

For these aligned/quadrant half-shift geometries, each physical HB edge supplies
1 TB/s, every memory supplies at most 1 TB/s, and each compute has at most four
neighbor memories with a 4 TB/s limit. All active demands are 4 TB/s. Under
free residency, assign each reachable bank to any active neighboring compute.
No HB edge then exceeds its parent memory's total 1 TB/s, and no compute exceeds
4 TB/s. Consequently the oracle optimum equals the aggregate service of the
**union of reachable banks**. This is a feasible construction achieving the
neighbor-bank cut bound; min-cut is not uncovering an additional bottleneck
in this particular budget regime. Its edge-category decomposition is nonunique.

If exactly A of N=36 clients are chosen uniformly, and bank b can be reached
by r_b distinct clients, its probability of being useful is
`1 - choose(N-r_b,A)/choose(N,A)`. Summing this times bank service gives an
exact expected oracle throughput, implemented in `w2w/analysis/analyze_bank_structure.py`.
For periodic XY each bank reaches exactly k distinct clients. Hence same-k
masks have identical expected oracle throughput under uniform subset activity.
This does not establish equivalence for correlated activity, fixed residency,
fairness or a tighter HB/controller budget.

For nine active clients the exact finite expectations, in TB/s per client,
are Aligned=1 for every k; X k=2 ranges 0.917--1.643 and X k=4 is 1.643;
XY k=2 ranges 1.411--1.616 and XY k=4 is 2.470. Thus in this oracle objective
X admits a two-port mask that matches its full-interface result, while adding
XY geometric neighbors does not necessarily improve a bounded-degree design.
These exact population means must not be substituted for individual held-out
or fixed-layout measurements.
