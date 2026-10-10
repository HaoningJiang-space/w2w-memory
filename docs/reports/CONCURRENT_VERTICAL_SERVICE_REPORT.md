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
between schedule and service distribution; the completed full cold results follow.

[Probe evidence](../../artifacts/provenance/static_placement/concurrent-probe.json)
contains exact sources/tools, audits, paired intervals and Gateway output bins.
Raw executions remain outside Git in `concurrent-probe-r1` under the isolated
hn072 archive. Gateway bins are 0.1 µs in the probe and 1 µs in the full study;
they record bytes/busy cycles without averaging execution or resolving every
within-bin burst.

## Full cold study: complete

All six new executions at `869f0ac` pass independent physical, command/ACK,
operand, arithmetic, finite-fetch and drain audits. All execute 490 tasks and
read 151,031,808 native bytes on the same 128 domains. The cross-schedule identity
gate checks identical mathematical tasks/tensor edges, compute placement, paired
weight addresses and physical data resources. S1 removes 96 Gate→Up barriers and
adds 64 previous-block→Up barriers, retaining the block boundary. S0 Reference
matches all 2,531,259 old physical events and the complete integer-ps result.

| Execution | Reference | Hybrid | Balanced | Phase-Split |
|---|---:|---:|---:|---:|
| S0 serial | 581.384 µs | 562.863 µs | 582.050 µs | **502.973 µs** |
| S1 independent Gate/Up | 580.576 µs | 604.804 µs | 569.089 µs | **456.627 µs** |

S0 Hybrid/Balanced reuse their independently audited `47e68e5` records, without
rerunning them. Their weight-layout hashes match the new S1 registrations. The
new S0 Reference migration gate preserves the default execution contract.

Phase-Split improves over matched S1 Reference by **21.349%**. Enabling S1 reduces
Phase-Split time by **9.214%**, but barely changes Reference (0.139%). Hybrid
becomes slower under S1; overlap is not automatically useful parallelism.
Unlike the small probe, full Phase-Split already improves under S0 (13.487%).
Thus concurrent projection service contributes, but is not its only mechanism.
The study does not attribute the entire benefit to deleting Gate→Up: bounded
fetch admission and round-robin issue are also explicit components of S1.

Actual hop-flits remain 52,536 / 418,356 / 1,167,416 / 470,616 by placement in
both schedules. Traffic volume alone does not explain the schedule interaction.
All layouts use the same compute peaks, two engine contexts, native domains,
HB lanes and receive/write ports. Additional S1 state uses the original SRAM.

[S0 audit](../../artifacts/provenance/static_placement/concurrent-s0-analysis.json),
[S1 audit](../../artifacts/provenance/static_placement/concurrent-s1-analysis.json),
[identity proof](../../artifacts/provenance/static_placement/concurrent-comparison-identity.json)
and [migration proof](../../artifacts/provenance/static_placement/concurrent-s0-migration-proof.json)
retain frozen sources, input/result hashes and observed resources.

## Matrix mechanism and the completion frontier

For this one-token, eight-active-expert input, each block has hidden dimension
4096 and intermediate width 128. Gate/Up each map a 4096-element input into 128
outputs; Down maps those 128 gated elements back into 4096 outputs. Each FP8
matrix has 524,288 data bytes plus 128 scale bytes. Equal weight byte counts
therefore do not imply equal dependency positions or intermediate-state needs.
X occupies 8,192 BF16 bytes, each G/U output 512 FP32 bytes, H 256 BF16 bytes,
and the Down partial output 16,384 FP32 bytes. The logical X is shared, while
lowering currently materializes explicit consumer copies; S1 is not a fused
FC1 or input-broadcast implementation.

The relevant readiness boundaries are:

\[
T_H\geq\max(T_G,T_U)+T_{\mathrm{activation}},\qquad
T_{D,\mathrm{start}}\geq\max(T_H,T_{W_d,\mathrm{ready}},T_{\mathrm{shared\ grant}}).
\]

The second boundary permits early Down-weight fetch in principle, while
preserving the activation dependency of its arithmetic. A controller that
waits for H before requesting Wd imposes an additional scheduling restriction.
Consequently, a placement result is conditional on how fetch admission exposes
these distinct frontiers to physical service.

Gate and Up share X and are mathematically independent. The activation joins
their completed dot products: for each intermediate element, SiLU and the product
require the corresponding complete Gate/Up reductions. Down computation then
uses that activation. **Down weights do not mathematically depend on H**, but
the current allocator still starts their fetch after activation. S1 separates
the two FC1 projections only; it does not remove this Down-fetch barrier, fuse
FC1, pipeline individual output elements, or prefetch the next block.

At a 32 B/ns gateway, two 524,416 B matrices require at least 32.776 µs of shared
payload service. On distinct gateways their optimistic joint work reference is
16.388 µs. Actual completion also pays native row/refresh constraints, command
admission, shared requester limits, transport and consumption. The 128 B/ns
fabric rate is a peak, not a guarantee of delivered service. Existing 256-flit
buffers, credit and contention continue to execute in BookSim.

Token reuse changes this balance. With n tokens per FP8 weight read, ideal
intensity is approximately n MAC/B. The declared 16,384 MAC/ns cluster peak
balances two 32 B/ns projection gateways near n=256, and a single Down gateway
near n=512, ignoring scales, native inefficiency and other work. These are
candidate-budget arithmetic references, not measured crossover points or
evidence that the assumed SRAM/activation dataflow can sustain those batches.
The current n=1 cold result cannot establish a prefill placement principle.

The matched final expert-62 block-8 observations under S1 are:

| Milestone | Reference | Balanced | Phase-Split |
|---|---:|---:|---:|
| Previous block accumulate / projection release | 513.171 µs | 522.747 µs | 410.271 µs |
| Both Gate/Up complete | 556.153 µs | 544.690 µs | 432.198 µs |
| Release-to-projection-join span | **42.982 µs** | **21.943 µs** | **21.927 µs** |
| Activation finish | 556.163 µs | 544.700 µs | 432.208 µs |
| Down finish | 577.983 µs | 566.496 µs | 454.034 µs |
| Layer finish | 580.576 µs | 569.089 µs | 456.627 µs |

Reference's two projections share `g0_3`; Phase-Split Gate uses `g0_3` and Up
uses adjacent `g0_2`. Their fetch windows overlap, and both gateways have actual
service in each of the 21 full 1-µs bins from 411 to 432 µs. This is binned
service evidence, not proof of continuously simultaneous service or attribution
of every byte in those bins to this block. S1 overlaps fetch windows in 83 of
96 Phase-Split projection pairs; two bounded slots do not promise every pair
is admitted together.

The final Down spans are almost equal: 21.820 / 21.826 µs for Reference /
Phase-Split. The observed 123.949 µs layer lead consists of an earlier block
release (102.900 µs), a shorter final projection-join span (21.055 µs), and a
small difference in the following stages. This is a matched dependency timeline,
not an exclusive decomposition of all shared-resource stalls.

Balanced also gets a roughly 22-µs final projection join, yet reaches that block
112.476 µs later than Phase-Split. It has a lower maximum gateway work bound,
but moves more matrices and changes the earlier physical service/feedback
timeline. This prevents attributing its disadvantage simply to the final
Gate/Up pair, average bandwidth, or one last network hop.

Gate/Down colocation is consequently a conditional design hypothesis: within
one block their computations are ordered, but other experts and contexts can
have Gate and Down demands live together. Placement must account for these
competing frontiers, rather than assume all matrices with different phase names
use a gateway at disjoint times. Matrix-ready interval overlap also differs from
actual payload service overlap and from availability of the matching activation.

## Final-operand observations and evidence limits

The descriptor completing the final Up prefix in that block has this observed
timeline:

| Event | S1 Reference | S1 Phase-Split |
|---|---:|---:|
| Request issued | 552.250 µs | 429.343 µs |
| MC accepted | 555.126 µs | 430.380 µs |
| Native accepted | 555.126400 µs | 430.380880 µs |
| Last array event | 556.111520 µs | 432.084160 µs |
| Gateway descriptor fully ready | 556.149 µs | 432.125 µs |
| Weight committed / prefix complete | 556.152 µs | 432.197 µs |
| Up compute finish | 556.153 µs | 432.198 µs |

The remote Phase-Split final-beat residual is 72 ns versus 3 ns locally, yet the
matrix join is much earlier. That residual is not the full network cost: the
response streams before the descriptor is fully ready. Request-to-MC intervals
also include finite admission waiting, even for Reference's colocated endpoint.
Native acceptance-to-array time is not shorter for this Phase-Split descriptor;
its earlier issue and the surrounding request feedback matter.

These captures are transaction-level. They retain packet admission/delivery and
aggregate actual BookSim hop counters, **not individual flit-hop timestamps**.
Empty per-descriptor link lists do not imply local transport. The read-only
stage analyzer now marks this distinction; it does not invent missing detail
or rerun frozen application executions. Packet windows include NI supply and
receive/write waiting, so they are not isolated propagation-delay measurements.

[Selected stage evidence](../../artifacts/provenance/static_placement/concurrent-stages.json)
retains all paired intervals, matched block milestones and final-prefix paths.
[Gateway series](../../artifacts/provenance/static_placement/concurrent-gateway-series.json)
retains all totals and the matched two-gateway example. Full per-task records and
all gateway series, with hashes, remain in the remote archive.

The next matrix-level question is which legal granularity should expose service:
an intermediate-dimension slice can produce independent gated elements; a split
along the hidden reduction dimension produces partial dot products that must
join before SiLU. They require different accumulator/readiness state. This
study uses complete 128-element blocks and does not establish fragment-aware
execution or a new fused-FC1 implementation. Further placement claims must keep
those numerical dependency and finite-state distinctions explicit.

## P4: complete, separately frozen

The earlier 24-token P4 remains at frozen `47e68e5`, with its same initial cache
and serial policy. It is not used to select this candidate or changed by S1.
Its independent audit is complete: Reference 13.281470 ms, Hybrid 12.496369 ms,
with 5.911% complete and 4.777% token-12–23 elapsed reduction. Observed misses,
reloads and native bytes are equal for every invocation. This supports the
earlier Hybrid layout under S0 and finite cache; it does not validate Phase-Split
or S1 in multi-layer execution. See the [P4 report](SIMULATOR_PERFORMANCE_PLACEMENT_REPORT.md#p4-completed-multi-layer-confirmation).

S2 bounded next-block prefetch is deferred. Array timing, aggregate SRAM banking,
ideal global receive booking and macro-network timing remain model conditions;
these results do not prove numerical inference, silicon accuracy or PPA.
