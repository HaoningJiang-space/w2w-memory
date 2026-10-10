# FFN stage timing and controlled gate/up intervention

The P0–P3 performance/placement stage and controlled gate/up intervention are
complete. The 24-token P4 confirmation is still running. Stage evidence does not
establish a universal placement principle; S1 now tests the stronger question
of independent projection fetch under finite resources.

## Correct comparison boundary

Balanced is not Hybrid plus remote gate/up. Its down gateway rule is different:
Balanced uses `3*local_block + phase_index`, while Hybrid uses `local_block` only
for down. Their physical matrix offsets can also differ. Existing cold results
remain valid, but their contrast cannot isolate gate/up locality.

The new **Hybrid gate/up intervention** locks the complete Hybrid down catalog,
including memory group, byte offset and size, across all 128 experts. Gate/up
gateway choices follow Balanced. Objects that do not move keep their addresses;
moving gate/up matrices fill free aligned intervals around the locked objects.
Compute tasks, dependencies, input placement, all hardware and arithmetic work
are unchanged. This changes gate/up physical placement and addresses, including
possible row locality; it is not a pure propagation-delay experiment.

Both Hybrid and the intervention execute at `7a694db`. The Hybrid rerun matches
the complete frozen `47e68e5` physical record, including every event and integer-ps
timing. No larger hardware or search is introduced.

| Controlled S0 layout | Completion | Hop-flits | Last native tail |
|---|---:|---:|---:|
| Hybrid | 562.863 µs | 418,356 | 560.157280 µs |
| Hybrid down + striped gate/up | 544.288 µs | 1,167,416 | 541.594160 µs |

Changing gate/up placement while keeping down's complete physical identity fixed
reduces completion by **3.300%**. It has the same hop-flit count as original
Balanced, yet is faster than its 582.050 µs. Thus the earlier hypothesis that
preserving local gate/up explains Hybrid's advantage is not supported by this
intervention. Changed addresses/row locality and request feedback remain part
of the gate/up intervention; this result does not allocate savings to one cause.

[Independent audit](../../artifacts/provenance/static_placement/gate-up-ablation-analysis.json),
[registration](../../artifacts/provenance/static_placement/gate-up-ablation-registration.json)
and [migration proof](../../artifacts/provenance/static_placement/gate-up-migration-proof.json)
retain exact sources, input/result hashes and observed resources.

## How stage time is measured

`w2w.analysis.ffn_stages` reads the independently audited immutable result and
checks its raw SHA. It records dependency completion, allocation, first/last
read issue, MC/native/array readiness observations, committed operand delivery,
context start/finish and actual arithmetic grants. It reconstructs contiguous
weight availability from descriptor offsets, including prefix holes and cache
hits.

Each started context clock is assigned to exactly one of:

- Its arithmetic/read service grant.
- No consumable prefix after scale service: operand wait.
- Operands ready but no grant yet: shared-service waiting.

These opportunities reproduce each task's integer-ps context span and every
cluster's existing arithmetic busy total. Required-input-to-start gaps are
recorded separately from in-context waiting. Tests cover an out-of-order prefix
hole, a ready context without a grant, cached operands and locked down-address
placement. Directed tests and all three full cold reconstructions pass on hn072.

Task/phase sums overlap across contexts and clusters. They must not be added into
system stall time. A latest-finishing-predecessor walk is a dependency timeline,
not proof of an exclusive critical path through all implicit resource contention.
Native array observations retain their original timestamp convention.

## Observed cold finish propagation

Reference and Hybrid both finish through expert 62. Reference's four partition
accumulators tie at 579.049 µs; Hybrid's latest is partition 0 at 560.528 µs.
Balanced instead finishes through expert 67. The matched expert-62 block-2
timeline is:

| Event | Reference | Hybrid | Hybrid earlier |
|---|---:|---:|---:|
| Previous block accumulate / block-2 dependency ready | 513.468 µs | 494.637 µs | 18.831 µs |
| Gate start | 514.184 µs | 495.222 µs | 18.962 µs |
| Gate finish | 535.266 µs | 516.459 µs | 18.807 µs |
| Up finish | 557.024 µs | 538.300 µs | 18.724 µs |
| Activation finish | 557.034 µs | 538.310 µs | 18.724 µs |
| Down finish | 578.791 µs | 560.270 µs | 18.521 µs |
| Partition accumulate finish | 579.049 µs | 560.528 µs | 18.521 µs |
| Expert reduce finish | 580.242 µs | 561.721 µs | 18.521 µs |
| Layer combine finish | 581.384 µs | 562.863 µs | 18.521 µs |

The final gate takes 21.082 / 21.237 µs of context time, up 21.164 / 21.250 µs,
and down 21.583 / 21.706 µs. Their earlier finishes therefore propagate an
earlier release rather than faster service of these particular GEMMs. The
sequence starts farther upstream: expert-62 block-0 accumulate is 84.510 µs
earlier in Hybrid, but much of that advantage is lost during block-1 gate waiting.
The final improvement is the surviving 18.521 µs, not the sum of phase savings.

The initial block-0 gate exposes where a large lead first appears in this branch:

| Expert-62 block-0 gate event | Reference | Hybrid |
|---|---:|---:|
| First descriptor issue | 145.571 µs | 145.759 µs |
| Context start / scales ready | 149.514 µs | 149.620 µs |
| Last descriptor issue | 337.790 µs | 188.422 µs |
| Last native descriptor acceptance | 340.682320 µs | 191.301280 µs |
| Last committed weight | 341.776 µs | 192.398 µs |
| Gate finish | 341.777 µs | 192.399 µs |

Its initial access and context start are almost unchanged, but its descriptor
issue span contracts from 192.219 to 42.663 µs. The returned operands and gate
finish follow that change. This is direct evidence of a changed issue/return
feedback timeline, rather than a 149 µs propagation improvement for one flit.
It does not isolate which shared memory/transport resource caused the earlier
issue opportunities; the controlled gate/up experiment tests an additional
intervention, not an attribution of all Reference-to-Hybrid savings.

Hybrid's summed down operand wait across all 96 cold down tasks is **3.457285 ms**,
versus **2.047937 ms** in Reference, despite the earlier final down finish. This
is another reason not to infer critical-path time from aggregate waiting sums.
The exact intervention is still required to identify the effect of gate/up
placement while keeping down placement fixed.

Evidence: [cold-stages.json](../../artifacts/provenance/static_placement/cold-stages.json).
Full per-task records remain in the remote archive. Execution is `47e68e5`;
stage analysis is `7a694db`. No native simulator or hardware model was changed
to obtain this analysis.

## Pending experiments and acceptance

P4 Reference/Hybrid remains frozen at `47e68e5`; it is not restarted or modified.
Acceptance checks complete and token-12–23 elapsed time, actual misses/reloads,
native/domain/gateway work, stage readiness and resource drain. Subsequent cache
traffic is observed, not forced equal. Both layers still reuse the same archived
routing and remain an FFN-only timing proxy.

The completed controlled cold pair uses `gate-up-ablation-r1` in the same
isolated remote archive. Once/minute monitors audit each completed study and
reconstruct stages. Failed runs stop for inspection and are not automatically
retried. Independent routing and physical-parameter sensitivity remain
subsequent work; no large DSE is required by these registrations.

## S1 and Phase-Split: frozen, running

S0 retains historical Gate→Up and previous-block-accumulate→Gate control edges.
S1 removes Gate→Up and keeps the previous-block barrier for **both** Gate and Up.
All mathematical tensor edges, arithmetic work, compute placement and reduction
order are unchanged. S1 allows both projection fetch and compute overlap; it does
not prefetch the next block.

The existing allocated/read-ready and compute-ready states are exposed through
two finite matrix fetch slots per cluster. Descriptor issue rotates among those
slots, still sharing the original two requests/cluster/cycle, 32 outstanding,
two compute contexts and one MAC/read grant per cycle. Full matrix storage remains
reserved. Two 64 B fetch entries plus an 8 B selector (136 B/cluster) are charged
inside existing SRAM. No MAC, SRAM data port, native domain, HB lane or fabric
port is duplicated. This is an explicit bounded admission/issue policy as well
as a dependency intervention; it is not merely deletion of a graph edge.

Phase-Split covers all 128 experts. It keeps Reference Gate and Down addresses
fixed and places Up at the adjacent same-row gateway, filling released aligned
Up slots. In this frozen cold input its gateway matrix counts become
18/18/15/21, with a 344.148 µs hottest-gateway payload work bound and one-third
remote weight payload. These are resource-work calculations, not predicted
execution times.

Small native FFN execution demonstrates overlapping Gate/Up request windows
and actual output observations at both gateways; independent audits check fetch
ownership, metadata SRAM, per-cycle issue, outstanding, MAC/read service, operands,
command/ACK, native bytes and complete drain. Dependency and existing native
regressions pass. Gateway payload/busy time series use 1 µs fixed bins in the
full study (0.1 µs in the probe); this records service without changing it and
does not resolve every within-bin burst. Tail analysis follows the actual final
prefix descriptor through request, native/gateway observations, recorded NoC
links, SRAM delivery and compute.

Execution source is `869f0ac`. `concurrent-service-r1` registers S0 Reference /
Phase-Split and S1 Reference / Hybrid / Balanced / Phase-Split. Six full cold
executions run at most two at a time, with minute monitoring, independent audits
and an S0 Reference migration gate. Old S0 Hybrid/Balanced evidence remains frozen.
No final S1 ranking is claimed before completions. See
[S0 registration](../../artifacts/provenance/static_placement/concurrent-s0-registration.json),
[S1 registration](../../artifacts/provenance/static_placement/concurrent-s1-registration.json)
and [launch](../../artifacts/provenance/static_placement/concurrent-launch.json).
