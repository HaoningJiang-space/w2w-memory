# Matrix state lifetimes: completed G1/G2 and the fragment decision

The saved-event analysis confirms a return-only ownership opportunity, but the
bounded controller intervention does **not** establish it as the dominant
performance bottleneck. In the fixed Phase-Split contention fixture, separating
issue from return state improves 66.894 → 64.935 µs (2.93%); three coupled slots
already reach 65.800 µs. The split implementation declares 440 B of control
state/cluster versus 200 B for three coupled slots. Fragment execution therefore
remains deferred. A separate completed S1 finite-cache pair confirms the
whole-matrix Phase-Split layout's persistent service benefit.

## G1: issuing and return-only ownership reconstructed from saved events

The twelve existing captures execute at `9fbb4db`. No G1 simulation is rerun.
Analysis at `f44de81`, followed by final readback at `7177e2e`, preserves all
previous case metrics, audits and release/issue effects. Each case has 72 matched
matrix acquire/release intervals. For each matrix:

- r: maximum required predecessor completion / mathematical release;
- a: funded fetch admission;
- z: final descriptor enqueued into the request path;
- c: final operand committed, when the coupled slot releases.

`[a,z)` denotes the issuing interval and `[z,c)` the return-only interval.
This is a state-lifetime partition, not an additive application stall breakdown.
The new controller must observe iterator exhaustion and retain return bindings;
it is not assumed to retire instantaneously at the post-hoc z timestamp.

| D1 + round-robin | Hybrid | Phase-Split |
|---|---:|---:|
| Makespan (µs) | 84.300 | 66.894 |
| Mean coupled ownership (µs/matrix) | 8.962444 | 7.049389 |
| Mean return-only ownership (µs/matrix) | 3.779236 | 3.456681 |
| Return-only / summed ownership | 42.17% | 49.04% |
| Delayed matrix admissions | 44 | 44 |
| Sum of admission waits (µs) | 286.081 | 228.452 |
| Maximum admission wait (µs) | 11.049 | 6.031 |

Across-task durations overlap. In particular, the faster Phase-Split has the
higher return-only fraction: minimizing that fraction is not the performance
objective.

Hybrid `e62/b8/up` is eligible at 60.872 µs and admitted at 68.002 µs. Its entire
7.130-µs wait coincides with both coupled slots being owned:

| Interval (µs) | Owners | Return-only owners |
|---|---|---|
| 60.872–60.953 | e108/b2/gate, e108/b2/up | e108/b2/gate |
| 60.953–64.005 | e108/b2/up, e62/b8/gate | none |
| 64.005–68.000 | e108/b2/up, e62/b8/gate | e108/b2/up |
| 68.000–68.002 | e108/b2/up, e62/b8/gate | both |

At least one owner is return-only for 4.078 µs; both are still issuing for
3.052 µs. Only 0.002 µs has both owners return-only. The corresponding
return-only slot×time is 4.080 µs. These measurements identify an opportunity,
not a replay-predicted 4.078-µs makespan saving.

## Behavior-preserving extraction accepted before intervention

`f735946` extracts the existing admission, arbitration and release behavior into
`system/fetch_scheduler.py`, retaining the original order and default records.
Thirteen relevant remote tests pass. The Hybrid and Phase-Split D1/round-robin
cases match the old **complete canonical physical record**, not just makespan:
84.300 / 66.894 µs, with 160,667 / 160,666 events and unchanged drain.

A separate four-worker trace gate compares original `9fbb4db` with candidate
`188fbdc` in default coupled mode. Full physical records, integer-ps timing,
ACT/PRE/RD/REF time/address command logs, native submit/supply/commit/boundary
mutations and returned flit/VC progress/completions have identical fingerprints.
Native tools are pinned to the previous accepted binaries. Source/build paths
are the documented canonicalization exceptions.

The first trace-gate analyzer stopped after the first complete pair because it
expected wall-clock speedup metadata from an equivalence-only capture. `6be612f`
corrects that requirement and adds readback; the successful first pair is reused,
the second pair is then run, and all four saved command captures are independently
audited. The failed analyzer/log is retained. No hardware timing or comparison
acceptance is relaxed.

## G2: nine fixed native controller interventions

Execution is frozen at `188fbdc`; final independent readback is `7177e2e`.
The fixture is the existing post-hoc expert-62/108 contention case:
hidden=1024, intermediate=1536, block=128, full 128-expert catalog, D1 release
and round-robin issue. It is not independent routing validation or the full
hidden=4096 cold FFN. All nine cells retain 9,439,488 native bytes, 124 tasks,
128 physical domains, the same mathematical work and layout-specific compute
placement. All three coupled-2 cells match their original complete records.

DRAM, HB, Gateway, NoC, physical SRAM, two compute contexts and shared MAC/read
grants remain fixed. Issue width remains two descriptors/cycle and outstanding
capacity remains 32/cluster. Extra associations and full matrices consume the
original SRAM, whose peak and final release are audited.

| Controller | Issue ownership | Return ownership | Declared control bytes/cluster |
|---|---|---|---:|
| coupled-2 | two matrices until all operands commit | retained in coupled slots | 136 |
| coupled-3 | three matrices until all operands commit | retained in coupled slots | 200 |
| split-2/R3 | two contexts until all descriptors are bound/issued | three associations until all replies commit | 440 |

The split budget is 2×64+8 B issue state, 3×16 B matrix associations and an
**additional** 32×8 B descriptor-binding table. Existing operand-prefix bitmaps,
matrix storage and common NI/request state remain separately funded. The extra
binding table is conservatively charged rather than treating Python labels as
free hardware. These are declared state bytes, not calibrated transistor area
or energy. This candidate has not demonstrated lower control cost.

| Placement | coupled-2 (µs) | coupled-3 (µs) | split-2/R3 (µs) |
|---|---:|---:|---:|
| Reference | 97.526 | 99.316 | 97.587 |
| Hybrid | 84.300 | 88.034 | 84.238 |
| Phase-Split | 66.894 | 65.800 | 64.935 |

For Phase-Split, split improves by 1.959 µs (2.93%) over coupled-2 and by
0.865 µs (1.31%) over coupled-3. Reference slightly regresses; Hybrid improves
by only 0.062 µs. Three coupled contexts are also not uniformly helpful.
Increasing admission changes contention and dependency release, not just a
local queue capacity.

Hybrid's motivating Up demonstrates this distinction directly:

| e62/b8/up milestone (µs) | coupled-2 | coupled-3 | split-2/R3 |
|---|---:|---:|---:|
| Eligible | 60.872 | 70.309 | 66.514 |
| Admitted | 68.002 | 70.309 | 66.514 |
| Final descriptor issued | 73.744 | 77.464 | 73.659 |
| Final operand committed | 77.564 | 81.328 | 77.523 |
| Issue context released | 77.564 | 81.328 | 73.659 |

The split case removes that task's admission wait, but eligibility moves
5.642 µs later, admission is only 1.488 µs earlier and final operand commit
only 0.041 µs earlier. Eliminating the observed wait does not save 7.130 µs
from the dependency chain. Full matrix/return ownership and downstream
competition remain finite.

Fifteen relevant remote tests pass, including return-tag capacity, premature
release and reused-association negatives. Final saved-result replay independently
checks every descriptor binding/commit, three-association and 32-binding limits,
SRAM funding, shared issue/outstanding/MAC/read constraints, physical service
bytes and complete drain. A final three-test analysis gate verifies the service
bounds' separate state-lifetime semantics. Test sets overlap; counts are not
added as distinct coverage.

## Service bounds and the fragment gate

`analysis/service_bounds.py` reports necessary Gateway/domain/HB/link/RX/shared
compute work and an arithmetic-only dependency bound. Terms are maximized,
never summed. They do not predict execution time or identify an exclusive
critical path through implicit resource competition.

The final analysis corrects the split case's finite-state work accounting:
operand delivery constrains return association occupancy, while descriptor
issue width constrains issue-only occupancy. The first analysis had reused the
coupled operand-hold bound for issue slots. Only derived bounds change; no
native run, makespan or controller choice is replaced. The corrected G1 readback
preserves all prior measured lifetime/effect metrics.

For possible future fragments, whole-matrix Down prefetch is a required strong
reference. With three dedicated equal services and enough storage/associations,
Down weights can fetch before H; an ideal whole-matrix payload schedule already
has M/B service work. The `(q+1)M/(qB)` fragment pipeline assumes Down fetch
waits for each H and is not a general lower bound. Actual compute still waits
for H, and all shared wafer resource/cost obligations remain.

**G3 is deferred.** G1 confirms long-lived return state; G2 confirms only a
small placement-dependent gain and no declared control-cost advantage. This is
insufficient to promote Split-Phase as a main contribution or use it as the
justification for fragment execution. No 128→32 run, numerical equivalence,
Down reordering, extra HB topology or fragment performance is claimed. The
unexecuted prototype is retained separately from the current source.

## Independent S1 finite-cache confirmation completed

The previously registered pair executes at `9160207`; it is independent of the
new split controller and retains two **coupled** slots. Both cases use 24 tokens,
two distinct layer-weight sets, the same Reference compute placement and initial
L0 cache state/order, 184 MiB finite cache within 192 MiB physical SRAM/cluster,
S1 dependencies, round-robin issue, shared compute/read services and the same
frozen native binaries. Optional simulator accelerators are disabled.

| Metric | S1 Reference | S1 Phase-Split |
|---|---:|---:|
| Complete sequence (ms) | 13.300139 | 10.979869 |
| Token-12–23 elapsed interval (ms) | 6.419167 | 4.862114 |
| Cache hits / misses | 9,492 / 4,332 | 9,492 / 4,332 |
| Native / Gateway bytes | 2,271,770,112 | 2,271,770,112 |
| Reload bytes | 648,178,176 | 648,178,176 |
| Late-window reload bytes | 591,541,248 | 591,541,248 |
| Fabric hop-flits | 2,101,704 | 8,390,324 |
| Cross-reticle hop-flits | 839,124 | 839,124 |
| Data-lane byte·µm | 3,985,203,763,200 | 14,449,467,443,200 |

Completion improves **17.45%**, and the late interval improves **24.26%**.
The equality of observed miss/reload traffic is checked after execution, not
forced by the protocol. The result supports persistent independent-service
benefit under finite cache capacity. It is not a Split-Phase result, nor the
older S0 Reference/Hybrid 5.91% pair. S1 changes observed cache traffic relative
to that older execution, which must not be silently combined with this pair.

The benefit retains a physical transport tradeoff: data-lane activity rises
about 3.63×, concentrated within reticles. There is no measured EDP/PPA claim.
Per-invocation traffic, exact stage milestones, ownership and latest-finishing
dependency chains are independently reconstructed. Stage sums overlap and the
chain does not establish exclusive causality for shared-resource waits. The
proxy reuses the routing across layers and excludes attention, KV, norm,
residual and numerical model execution.

## Evidence and recovery

Compact/derived receipts, registrations, tests and SHA-bound archive identities
are in `artifacts/provenance/fetch_state`. Raw captures, commands and full stage
reconstructions remain under
`/Projects/haoning/w2w-full-system-matrix-service-20261010` on hn072:

- `fetch-factor-r1/lifetimes-readback-7177e2e.json`: all twelve G1 cases;
- `split-fetch-r1/independent-readback-7177e2e.json`: all nine G2 interventions;
- `fetch-controller-tracegate-r1/analysis.json`: detailed migration trace gate;
- `hierarchy-analysis-r1/placement-analysis.json` and `stages.json`: S1 cache pair.

The gate preserves valid negative results and failed analysis attempts. No
performance-dependent retries or expanded candidate search were used. The
default execution contract remains coupled; split execution is opt-in and
cold-only. Further hardware work needs evidence that it improves the best
whole-matrix service baseline at an acceptable physical cost.
