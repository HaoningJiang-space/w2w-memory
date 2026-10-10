# FFN stage timing and controlled gate/up intervention

The P0–P3 performance/placement stage is complete. The 24-token P4 confirmation
is still running. This report adds descriptive stage evidence and a registered
controlled intervention; it does not strengthen the architecture claim before
P4 completes.

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

Both Hybrid and the intervention are registered under execution source
`7a694db`. The Hybrid rerun will be compared against the complete frozen `47e68e5`
physical record to check migration equivalence. No new optimized placement
strategy, search or larger hardware is introduced.

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

The controlled cold pair uses `gate-up-ablation-r1` in the same isolated remote
archive. Once/minute monitors audit each completed study and reconstruct stages.
Failed runs stop for inspection and are not automatically retried. Independent
routing and physical-parameter sensitivity remain subsequent work; no large DSE
is required by these registrations.
