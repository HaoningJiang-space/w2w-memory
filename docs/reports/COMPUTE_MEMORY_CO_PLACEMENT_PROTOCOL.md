# Up computation near vertically supplied weights: registered mechanism gate

Fetch-controller optimization and fragment execution are closed/deferred after
the completed state-lifetime gate. The next comparison changes **only where Up
arithmetic executes** on the existing compute wafer. It adds no PIM, HB lanes,
Gateway, router, MAC, native DRAM service or simulator kernel.

## Cold intervention

All three cells retain the full frozen Phase-Split weight catalog and addresses,
the `c0_b1` mathematical workload and S1 dependencies. Gate, Activation, Down,
ordered accumulators, reductions and token source/combine remain at the original
Reference compute locations. The graph's X, G, U, H and output DataEdges are
identical; changed endpoints use normal BookSim packets and finite SRAM service.
Input copies are explicit per consumer; no free multicast, input alias or gather
is introduced.

| Compute policy | Up position | Purpose |
|---|---|---|
| reference_compute | original Gate-side cluster | exact 456.627-µs frozen Phase-Split/S1 reference |
| up_local_compute | existing cluster at Up's actual Gateway router/position | trade large remote weights for small X/U transfers |
| up_matched_nonlocal | another existing same-reticle cluster, away from both Gate and Up Gateway | match per-cluster Up work while removing weight locality |

Co-location follows the declared physical Gateway landing/router, not the nearest
domain-center heuristic. Heterogeneous compute-profile changes are rejected.
The Up-local rule is catalog-derived and does not optimize against evaluation
routing or future cache state.

The nonlocal cell is a **cold diagnostic**, not another proposed static policy.
A deterministic matching uses the already known call's Up operations and the
Up-local destination counts. It preserves the exact per-cluster task/MAC/read/
scratch work distribution within equal-work groups, excludes both the original
and weight-local destination, and stays within the same reticle. If a call
cannot satisfy this contract it is rejected; no different workload is searched.
The frozen full cold call admits this control. Matching does not freeze dynamic
request arbitration, predecessor times or source-to-input distances. Its outcome
therefore cannot isolate an exclusive latency component, but avoids interpreting
a different static compute workload as a locality-only comparison.

All cells retain 16 clusters, two compute contexts/cluster, one shared MAC/read
grant, two coupled fetch slots/136 B state, two descriptor issues/cycle,
32 outstanding requests, finite physical SRAM and the same DRAM/HB/Gateway/NoC.
Whole matrices and original FP8 scales remain materialized. Native refresh,
command/ACK, receive service and contiguous-prefix operand readiness stay active.
Optional simulator accelerators and split return state are not enabled.

The single-block byte comparison (524,416 B Up weight versus 8,192 B X plus
512 B U for one token) is a logical payload motivation. Actual X origins,
repeated copies, headers, routes and traffic competition are charged by execution.
No energy/EDP estimate or universal batch crossover is asserted.

## Finite-cache extension

Before inspecting cold performance, register the same 24-token/two-layer workload
and the Reference-compute / Up-local pair. The full Phase-Split weight addresses
and arithmetic remain fixed. Both retain 184 MiB cache and 512 tag entries within
192 MiB physical SRAM/cluster, finite LRU/lookup/pinning and S1 resource limits.

The entire L0 weight catalog is initially resident, as in the accepted reference.
For Up-local, each **Up cache object actually resides at its new Up consumer**;
Gate/Down initial objects retain their original locations. The object set,
object iteration order and total preload bytes remain identical. Per-cluster
capacity and tag-entry limits are checked before execution. This is an explicit
independently preloaded warm-start condition, outside the measured interval;
neither migration nor remote hits are free. Its initialization cost is reported
as bytes, not claimed to have been timed. Initial per-cluster order, subsequent
eviction and cache traffic may change and must be reported.

The sequential FFN proxy reuses archived routing at both layers and has distinct
layer weight identities. It excludes attention, KV, norm/residual and numerical
inference. It is not a complete Transformer or a prefill study.

## Verification and execution

Mapping/execution code is introduced at `d31f03c`. Sixteen remote tests pass,
covering unchanged old mapping/dependency contracts, matched nonlocal work,
invalid local placement and stale warm Up preload negatives, and small native
cold/cache cases. Native cases retain shared resources, real U transfers,
local Up weight delivery, cache hits/evictions/reloads and complete drain.

The independent co-placement checker fixes mathematical tasks except their Up
tile, all DataEdges/control dependencies, weight/scale addresses and physical
resources. Saved-result replay verifies actual MACs, source/input/graph identity,
native/Gateway bytes, finite compute/fetch/outstanding/RX/SRAM, cache service,
preload destinations and drain. Reference-compute must match the accepted cold
and cached Phase-Split **complete canonical physical records**, not only timing.
Baseline execution identities remain `869f0ac` and `9160207` respectively.

Execution uses the same BookSim binary
`9d18611aa0cc74b6d8a475e302134c7888b1417648607abce3a6f8d04311e308`
and Ramulator bridge
`37eb00768993fb5cfd903c690e72a21cdc69e10f4acbc421762f54dc5a33ba54`.
No native simulator/build or kernel change is made for this gate.

The new isolated root is
`/Projects/haoning/w2w-full-system-co-placement-20261010` on hn072. Immutable
source/input registrations precede execution. `tools/monitor_co_placement.py`
runs all three cold cells, independently audits them, then starts both frozen
multilayer cells if correctness passes. It does not select cases using latency,
discard negative results or automatically retry failures. Raw captures remain
outside Git. Source/input/native/raw SHA receipts and test logs will be published.

Acceptance reports makespan and native tail; actual NoC data-lane byte·µm and
intra-/cross-reticle hops; committed remote weight/X/U endpoint payload;
per-Gateway/domain service and queue observations; planned and actual per-cluster
MAC/read work, SRAM peaks and context occupancy; phase/tail readiness;
warm preload and per-invocation/late-window miss, reload and native bytes.
Payload counts are distinct from actual flit distance. Context/wait/stage sums
overlap and are not additive critical-path delay. Traffic reduction is not a
calibrated energy or PPA result. No Up-local performance conclusion is claimed
at registration.

## Status after the cold gate

All three cold cells complete and pass independent saved-result audit. The
original-Up reference exactly reproduces the old complete Phase-Split physical
record. Up-local takes **451.676 µs versus 456.627 µs**, while NoC data-lane
activity decreases **87.78%**; matched nonlocal takes 517.708 µs. The fixed warm
pair starts after correctness acceptance and remains running. See the
[result report](COMPUTE_MEMORY_CO_PLACEMENT_REPORT.md) for the matched tail
timeline, transport/cost interpretation and explicit pending multi-layer state.
