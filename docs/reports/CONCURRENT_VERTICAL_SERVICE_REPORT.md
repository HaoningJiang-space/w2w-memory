# Dependency policy and concurrent vertical service

This study tests whether placement benefits depend on legal projection
concurrency. It retains the historical S0 graph, and adds S1 with independent
Gate/Up plus bounded fetch/issue state. It does not implement PIM, next-block
prefetch, fragment placement, extra memory service or extra compute throughput.

## Frozen comparison

S1 keeps mathematical tensor edges and ordered accumulation, and preserves the
previous-block barrier for both Gate and Up. Two fetch entries and their selector
pay 136 B inside each cluster's existing SRAM. Full matrices still occupy SRAM.
The two compute contexts, one shared MAC/read grant, two request issue slots per
cycle and 32 outstanding requests remain unchanged. Read issue rotates among
the bounded fetch entries; this funded admission/issue policy is an explicit
part of S1, not an invisible schedule change.

Phase-Split locks Reference Gate/Down addresses across the complete 128-expert
catalog and moves only Up to the adjacent same-row gateway. It uses no evaluated
routing or expert-hotness information. For the full cold input the busiest
gateway payload work bound is 344.148 µs, compared with Reference 442.476 µs.
That bound is not a performance prediction.

The full study is frozen at `869f0ac`: S0 Reference/Phase-Split and S1
Reference/Hybrid/Balanced/Phase-Split. At most two cases run concurrently; all
cases retain the same native binary/bridge and physical service budgets. Old
S0 Hybrid/Balanced remain frozen comparison evidence, with separate provenance.
The S0 Reference rerun also has a complete physical-record migration gate.

## Small native mechanism probe: complete

The probe uses hidden=1024, intermediate=512, block=128, four catalog experts,
one active expert and four partitions on the same physical machine. All cases
read **1,573,248 native bytes** and pass independent operand, compute, SRAM,
native, command/ACK, finite fetch and drain audits. Its source is `558e2c1`;
the model/build inputs match the full-study source. This is a mechanism check,
not a full-size or complete-Transformer speedup.

| Execution | Reference | Phase-Split |
|---|---:|---:|
| S0 serial | 17.282 µs | 17.794 µs |
| S1 independent Gate/Up | 17.204 µs | 11.556 µs |

For block 0, S0 has zero Gate/Up fetch and context interval overlap in both
layouts. Under S1 Phase-Split, the fetch intervals overlap for 5.841 µs, native
array observation intervals for 5.673840 µs, and compute contexts for 5.601 µs.
Actual output bins contain service at the two independent gateways. Shared
arithmetic and requester limits are independently replayed, so these overlaps
do not copy MACs, native controllers or receive ports.

S1 Reference has a longer 10.654 µs fetch overlap yet finishes later: interval
overlap alone is not throughput or useful parallelism. Its two matrices still
share the same physical service group. The probe establishes an interaction
between schedule and service distribution; full cold results are still running.

[Probe evidence](../../artifacts/provenance/static_placement/concurrent-probe.json)
contains exact sources/tools, audits, paired intervals and Gateway output bins.
Raw executions remain outside Git in `concurrent-probe-r1` under the isolated
hn072 archive. Gateway bins are 0.1 µs in the probe and 1 µs in the full study;
they record bytes/busy cycles without averaging execution or resolving every
within-bin burst.

## Full cold study and P4: pending

`concurrent-service-r1` on hn072 runs the registered six cold cases with a
60-second controller. Completed executions are independently audited, then
`ffn_stages` reconstructs projection overlap and final-operand paths through
request, native/gateway observations, actual NoC link events, SRAM commit and
compute. Opposing component waits are not added into total stall time.

The earlier 24-token P4 remains at frozen `47e68e5`, with its same initial cache
and serial policy. It is not used to select this candidate or changed by S1.
Its final complete and late-window times, misses/reloads and stage observations
must be reported before drawing conclusions about multi-layer behavior.

S2 bounded next-block prefetch is deferred. Array timing, aggregate SRAM banking,
ideal global receive booking and macro-network timing remain model conditions;
these results do not prove numerical inference, silicon accuracy or PPA.
