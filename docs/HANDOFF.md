# Current handoff

Architecture V3 P0–P6 is complete and frozen at `5600528`. Continue
`w2w-memory`; do not restart machine/directory refactoring, replace the kernel,
or change the sibling simulator/RTL workspaces. Computation is on the logic
wafer, not PIM. Current machines use independent physical/native resource
identities and explicit mapping with the existing BookSim/Ramulator executor.

## Completed checks and comparisons

The read-only equal-byte RWDL probe at `f308299` is independently audited:
256 KiB takes **11.087 µs across eight existing domains**, versus **84.779 µs on
one**. Actual command/address multisets, ACT/PRE/RD/REF gaps, callback timing,
control and finite vertical drain pass. This is service parallelism, not an
application speedup, WR validation or silicon calibration.
[RWDL_SERVICE_DOMAIN_REPORT](reports/RWDL_SERVICE_DOMAIN_REPORT.md) and
`artifacts/provenance/rwdl_domains` retain identities and raw trace hashes.

The full-size cold contiguous-operand pair at `8a8e34b` is complete and
independently audited: **Central+ 782.060 µs, Distributed 581.384 µs**, reducing
completion by **25.6599%**. Same graph/addresses/placement, native service,
data/HB/output budgets, two shared-service contexts, finite admission-priority
selectors at all routers, request/ACK and refresh; no cache. Prefix metadata is
paid and drained. Extra Distributed control/layout resources are separately
reported, not declared equal PPA. Source HOL-with-credit observations are zero
on both. Middle x/y cut traffic is identical; the weight-flow difference is
mainly inside each region. Distributed retains a 3:1 gateway load imbalance.
[OPERAND_AWARE_ACCESS_REPORT](reports/OPERAND_AWARE_ACCESS_REPORT.md) and
`artifacts/provenance/operand_access` contain matched proofs and raw identities.

The 24-token two-layer finite-cache study at `3fb523e` is also complete and
independently audited: **Central+ 15.030022 ms, Distributed 13.281470 ms**, an
**11.6337%** reduction. Both have 2,265,477,120 native bytes and 641,885,184 reload
bytes, with identical traffic counts for every layer invocation. Separate
actual-event analysis at `1a92654` finds token 12–23 still reads 1,019,464,704 B,
including 585,248,256 B reload; its elapsed reduction is 12.7201%. This is a
finite late window, not a stationary trace. The cached study retains its frozen
byte-count operand policy and R3 binary; do not relabel it as the new prefix run.
[TWO_LAYER_CACHE_REPORT](reports/TWO_LAYER_CACHE_REPORT.md) and
`artifacts/provenance/memory_hierarchy` preserve audits and all raw hashes.

The warm whole-layer reference remains **658.065 µs, 6,912 hits, zero native
weight reads** across 24 tokens. Initial 2,416,508,928 B residency was outside
measurement and has a separate startup bound. Finite 184 MiB cache is within
192 MiB SRAM per cluster. Keep [WARM_LAYER_REFERENCE](reports/WARM_LAYER_REFERENCE.md)
and the registered [MEMORY_HIERARCHY_PROTOCOL](reports/MEMORY_HIERARCHY_PROTOCOL.md).
Zero reload is a valid negative observation, not a completion failure.

## Evidence and remote state

Raw captures/builds remain outside Git under
`/Projects/haoning/w2w-full-system-gateway-cache-20261009` on hn072. Frozen
`execution-hierarchy-r1` and `execution-operand-access-r1` worktrees must not be
reset. Both studies and their 60-second monitors completed successfully; there
is no pending application result in these registrations. The old r1 monitor
log is retained, current hierarchy monitoring evidence is
`periodic-hierarchy-r2.log`; cold pair evidence is `operand-access-r1/monitor.log`.

Relevant negative-result/metadata checks and selected integer-ps migration
fields at `5e7bd31` pass unchanged: C 54.489 µs, D 54.143 µs, corrected External
54.748 µs. R4 BookSim was built at `9a787a7`; exact native build-input hashes
match the later cold execution. R3 remains the cached execution's original
binary. Review evidence is in `artifacts/provenance/review_acceptance`.

## Current performance and placement stage

P0–P4 are complete and independently audited. The
[performance/placement report](reports/SIMULATOR_PERFORMANCE_PLACEMENT_REPORT.md)
and `artifacts/provenance/{simulator_performance,static_placement}` retain the
profiling breakdown, exact full-size equivalence proof, cold audits and frozen
multi-layer registrations. Total trace-gate wall time including audit/save falls
1,052.950 → 487.330 s for Central+ and 611.048 → 294.213 s for Distributed
(2.161× / 2.077×). Every physical record, native command/address/timestamp and
endpoint/flit trace matches; makespans remain 782.060 / 581.384 µs.

Memory-only policies cover all 128 experts and keep Reference compute placement
and initial cache residency fixed. Cold Reference / Balanced / Hybrid are
581.384 / 582.050 / 562.863 µs. Hybrid improves by 3.186%; the most uniform
Balanced policy is slightly slower. Locality is an exact Reference alias.
No gateway, domain, HB, SRAM or compute resource was added.

P4 Reference/Hybrid runs used frozen source `47e68e5` and contiguous-prefix
operands. The new archive is
`/Projects/haoning/w2w-full-system-performance-placement-20261010` on hn072:
`placement-multilayer-r1`, `execution-fast-r3`, `analysis-r1` and `monitor-r1`.
Both complete and pass independent analysis at `9d0ec5d`: 13.281470 /
12.496369 ms (5.911% reduction), late token-12–23 6.373886 / 6.069437 ms (4.777%).
Every invocation has equal observed miss/reload traffic; total native bytes are
2,265,477,120 and reload bytes 641,885,184. Controller log:
`logs/placement-controller-r1.log`; no automatic retries. Do not reset these
worktrees. This prefix registration is separate from historical byte-count runs.

Continue mechanism analysis using completed cold and P4 records. Compare
actual native/gateway service, row behavior, source opportunities and executed
region-local traffic; do not add overlapping waiting counters as total stall.
The P4 audit checks fixed compute/preload/storage/resource identities, invocation
misses/reloads and drain. A valid negative placement or zero-reload result remains
acceptable; equality of observed traffic was not an acceptance requirement.

The [stage mechanism report](reports/PLACEMENT_STAGE_MECHANISM_REPORT.md) now
reconstructs exact context clocks and milestones from all three audited cold
records. Reference/Hybrid finish through expert 62; the final block inherits an
18.831 µs earlier dependency release, surviving as 18.521 µs earlier layer finish.
Its individual gate/up/down context durations are slightly longer, not shorter.
Do not claim Balanced isolates gate/up locality: its down mapping differs.

The controlled cold pair at `7a694db` in `gate-up-ablation-r1` is complete:
Hybrid 562.863 µs versus striped gate/up 544.288 µs (3.300% improvement).
`hybrid-gate-up-striped` changes only gate/up physical placement, preserving
all Hybrid down memory/offset/size identities and every unmoved object. It is
an intervention, not an additional optimized policy. This does not support the
earlier hypothesis that preserving local gate/up is Hybrid's principal benefit.
Hybrid rerun matches every old physical result/event. `stage-monitor-r1` at
`d35d2ad` checks the pair once/minute, audits/stage-analyzes it and verifies the
Hybrid rerun against the old full physical record. Its second monitor waits for
P4's original audit and then derives actual pressure and stage observations.
Logs: `logs/stage-monitor-{gate-up,p4}-r1.log`; no automatic retries.

New steering prioritizes dependency-aware memory concurrency. Source `869f0ac`
has tested S1: independent Gate/Up, previous-block barriers retained for both,
two paid fetch slots, round-robin descriptors, unchanged shared issue/outstanding,
MAC/read and two compute contexts. Phase-Split moves only Up to its adjacent
same-row gateway, freezing Gate/Down addresses across the full catalog.
`concurrent-service-r1` now runs six registered cold cases, max two at a time,
with minute controller checks in `logs/concurrent-service-controller-r1.log`.
Execution worktree: `execution-concurrent-service-r3`. After completion, audit
the S0/S1 matrix, actual projection overlap, gateway service bins and final
operand paths. Do not add S2, fragments or a larger matrix before this result.
P4 remains untouched at `47e68e5`; subsequent cache traffic must be observed.

## Limits

No search/DSE, new fanout/endpoint RTL, partitioning rewrite, thermal/yield
project or additional hardware is required by the completed comparison.
Optimized central fanout, fair external I/O cost, prefill and a complete
Transformer remain unmeasured. The two-layer study reuses archived routing at
the second layer and excludes attention/KV/norm/residual/numerical execution.
Ideal global RX booking, aggregate SRAM banking and assumed array timing remain
explicit. Do not promote these resource proxies to product-calibrated PPA.
