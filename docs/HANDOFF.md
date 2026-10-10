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

## Next question and limits

Investigate static placement versus locality under the current fixed domain,
gateway and fabric budgets. The cold Distributed gateway bound (442.476 µs)
exceeds its hottest-domain interface bound (415.931200 µs), while some gateways
are lightly used. Do not assume more ports or a better controller will win.
Any placement must freeze the full catalog, preserve compute work/resources and
pay remote traffic; do not remap only the evaluated active experts for free.

No search/DSE, new fanout/endpoint RTL, partitioning rewrite, thermal/yield
project or additional hardware is required by the completed comparison.
Optimized central fanout, fair external I/O cost, prefill and a complete
Transformer remain unmeasured. The two-layer study reuses archived routing at
the second layer and excludes attention/KV/norm/residual/numerical execution.
Ideal global RX booking, aggregate SRAM banking and assumed array timing remain
explicit. Do not promote these resource proxies to product-calibrated PPA.
