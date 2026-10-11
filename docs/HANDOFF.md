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
`d35d2ad` completed both the pair audit/stage/migration gate and the P4
pressure/stage reconstruction after the original P4 audit.
Logs: `logs/stage-monitor-{gate-up,p4}-r1.log`; no automatic retries.

New steering prioritizes dependency-aware memory concurrency. Source `869f0ac`
has tested S1: independent Gate/Up, previous-block barriers retained for both,
two paid fetch slots, round-robin descriptors, unchanged shared issue/outstanding,
MAC/read and two compute contexts. Phase-Split moves only Up to its adjacent
same-row gateway, freezing Gate/Down addresses across the full catalog.
`concurrent-service-r1` completed all six registered cold cases and independent
stage audits; execution worktree is `execution-concurrent-service-r3`. S0
Reference/Phase-Split are 581.384 / 502.973 µs; S1 Reference/Hybrid/Balanced/
Phase-Split are 580.576 / 604.804 / 569.089 / 456.627 µs. Phase-Split improves
over matched S1 Reference by 21.349%; enabling S1 improves its own S0 time by
9.214%. The slower S1 Hybrid is retained. Identity proof at `e3316ee` checks
mathematical work, frozen paired layouts, physical budgets, and exact allowed
control changes. S0 Reference matches the complete old physical record.

The [matrix mechanism report](reports/CONCURRENT_VERTICAL_SERVICE_REPORT.md)
records final expert-62 block-8 projection joins: Reference 42.982 µs versus
Phase-Split 21.927 µs. An earlier block release also contributes; Balanced has
a roughly 22-µs final pair but arrives at it much later. Gate/Down temporal
reuse within one block does not imply no conflict between different experts.
No S2 or new hardware was introduced. That cold S1 result stays frozen; P4
confirms the separately frozen S0 Hybrid under observed finite-cache traffic.
The later registered S1 finite-cache pair is now complete, as recorded below.

Transaction-level captures retain packet windows and aggregate executed hops,
not per-flit hop timestamps. The read-only analyzer marks this; no absent trace
is treated as a local route. Analysis/test-only worktree `analysis-concurrent-final-r1`
at `807c62a` passed stage regressions and retained all gateway time series without
new simulation. All study/monitor logs and raw hash-bound files remain archived.

## Matrix service continuation

The [matrix-service protocol](reports/MATRIX_SERVICE_PROTOCOL.md) registers the
S1 Reference/Phase-Split 24-token two-layer pair at `9160207`. Both workers and
independent placement/stage readbacks complete under
`/Projects/haoning/w2w-full-system-matrix-service-20261010` in
`concurrent-hierarchy-r1` / `hierarchy-analysis-r1`, without automatic retries.
Times are **13.300139 / 10.979869 ms (17.45% reduction)**; token-12–23 elapsed
times are **6.419167 / 4.862114 ms (24.26% reduction)**. Both have 9,492 hits,
4,332 misses, 2,271,770,112 native bytes and 648,178,176 reload bytes. Lateral
data-lane activity grows about 3.63×; no measured PPA/EDP claim follows.
Fixed Reference compute placement,
initial L0 cache contents/order and physical resources are retained. Optional
compute-epoch and interactive acceleration are disabled in these executions.
Eleven relevant remote tests pass, including native S1 hits/evictions/reloads
and fetch/cache drain; the default S0 sequence input fingerprint is unchanged.

The fixed-slot probe at `9fbb4db` is complete: twelve native cells cross D0/D1
release, ordered/round-robin issue and Reference/Hybrid/Phase-Split. All have two
funded fetch slots, two shared-service contexts and identical 9,439,488 native
bytes/124 tasks/128 physical domains. D0 is not old unbounded-fetch S0. Hybrid's
dependency effect changes from −1.502 µs under ordered issue to +1.094 µs under
round-robin; Phase-Split improves under both. Independent readbacks preserve
all prior metrics and add exact finite-slot ownership at `d2b4893`. The two
experts are a post-hoc contention fixture, not independent routing validation.
Registrations, raw hashes and saved-result audits are in
`artifacts/provenance/matrix_service`.

The [state-lifetime gate](reports/FETCH_STATE_LIFETIME_REPORT.md) now completes
G1/G2. G1 reuses all twelve captures; 4.078 µs of Hybrid's motivating 7.130-µs
admission interval has at least one return-only owner. The controller is
extracted at `f735946`, with full record equivalence and a separate detailed
ACT/PRE/RD/REF and endpoint fingerprint gate against `9fbb4db`.

Nine G2 cases at `188fbdc` compare coupled-2, coupled-3 and split-2/R3 with
identical data hardware/shared issue/outstanding/MAC resources. Final readback
at `7177e2e` passes all cases. Phase-Split takes **66.894 / 65.800 / 64.935 µs**;
declared control state is **136 / 200 / 440 B/cluster**. Hybrid's admission wait
vanishes under split, but final makespan improves only 0.062 µs. Thirteen
extraction tests and fifteen overlapping split tests pass remotely; three final
bound/lifetime tests pass. Return associations/tags are paid, independently
audited and drained. Coupled-2 defaults retain exact old records. The split
candidate is opt-in, cold-only, and has no demonstrated control-cost advantage.
Archive receipts are in `artifacts/provenance/fetch_state`; source/native/raw
SHA identities and retained analyzer failures are included.

G3 fragment execution remains deferred: current state separation provides too
little benefit to justify that expansion. The unexecuted fragment prototype is
retained in a named local stash, not mixed into current source or evidence.
Further work needs a strong whole-matrix Down-prefetch reference and a physical
cost argument before introducing fragments/topology. Any eventual 32-element
intermediate slice must retain original 128×128 scales, actual Down storage and
FP32 accumulation resources; no free gather or numerical-equivalence claim.

## Current architecture task: Up compute/memory co-placement

The Fetch Controller optimization branch is closed and Fragmentation remains
deferred. The [co-placement report](reports/COMPUTE_MEMORY_CO_PLACEMENT_REPORT.md)
and [frozen protocol](reports/COMPUTE_MEMORY_CO_PLACEMENT_PROTOCOL.md) now test
moving only Up arithmetic, keeping Phase-Split addresses, Gate/Activation/Down,
all mathematical edges and physical resources fixed. Mapping is introduced at
`d31f03c`; execution/source-input freeze is `02dab2a`; final cold readback is
`3b7851a`. No kernel/native/topology or hardware resource is changed.

Three full cold cases complete with independent audits. Original Up compute,
Up-local and per-cluster-work-matched nonlocal take **456.627 / 451.676 /
517.708 µs**. Up-local improves latency only 1.08%, but data-lane byte·µm falls
**794,654,284,800 → 97,132,108,800 (87.78%)**, and all 50,343,936 B remote Up
weight payload becomes local. Real U→Activation traffic is 49,152 B; X is still
transferred and charged. Native bytes, per-Gateway bytes and per-domain work
remain equal. Actual per-cluster MAC/read work matches the nonlocal control.
The original-Up record matches the complete old `869f0ac` Phase-Split record.
Earlier release of the final block is largely offset by slower Gate progress;
activity reduction does not identify equivalent latency savings. Sixteen remote
tests and three overlapping readback/mapping tests pass.

The registered 24-token two-layer pair completed at the same `02dab2a` source under
`/Projects/haoning/w2w-full-system-co-placement-20261010` on hn072. Both native
workers exit 0. Both preload the full same L0 catalog/global
order and 2,416,508,928 B outside measurement. Up-local relocates 1,536 actual
Up cache objects to their real consumers, without free remote hits or simulated
migration. Each cluster initially has 151,031,808 B / 288 entries, within the
same 184 MiB / 512-entry cache. Later miss/reload counts may differ; do not force
traffic equality or reject negative results.

The separate analysis-only finisher (`04f2e70`) completed
independent warm traffic/readiness/resource evidence against
the old `9160207` Phase-Split reference. It writes `multilayer/independent-readback.json`,
`completed-summary.json` and `COMPLETED_RESULTS.md` in the archive; no native
retry or performance selection. Completion **10.979869 → 9.656156 ms (12.06%)**,
late window **4.862114 → 3.918970 ms (19.40%)**, lateral byte-distance **72.15%**
lower. Native bytes fall **11.17%** and reload **39.16%**; this is not a
same-traffic-only speedup. The original controller's redundant postprocessing
was SIGKILLed after both workers finished; the independent finisher succeeded.
Retain both logs. Do not rerun simulation because that reader failed.
Current registrations, source/native/raw hashes, preload and test receipts are
in `artifacts/provenance/co_placement`; execution worktrees remain immutable.

The read-only [competition/energy continuation](reports/COMPUTE_MEMORY_COMPETITION_ENERGY_REPORT.md)
is implemented at `0d8ab50`. Six cold/warm Reference-weight, Phase-Split and
Up-local captures pass raw-SHA-bound reconstruction; five targeted remote tests
pass. The final Gate has **3.539 µs fetch-full wait, 38.773 µs missing-prefix
context clocks, zero ready-grant or compute-context-full wait**. Its issue span
is **38.737 µs**, intersecting a full unchanged MC pool for **38.504 µs**, with
no full requester-outstanding window. These intersections overlap and are not
removable stall savings. No compute scheduler/hardware change is justified.

`energy_edp.py` exposes complete activity coefficients, optional SHA-bound
command receipts, exact EDP thresholds and parameter-box extrema. All covered
warm EDP coefficients favor Up-local under shared nonnegative coefficients;
unknown residuals still prevent calibrated total energy/PPA claims. Full
application ACT/PRE/REF traces/currents and PE-internal SRAM/clock activity are
missing. Source catalog is `configs/analysis/energy_sources.json`; primary
65nm/DSENT/HB references are not transplanted into modern wafer pJ values.
Competition reader source: `competition-source-r2` / `0d8ab50`; outputs: `competition-analysis-r2`;
logs: `logs/competition-tests-r2.log`, `logs/competition-analysis-r2.log` in the
same own archive. Derived receipts are in `artifacts/provenance/competition_energy`.
Final Energy/EDP reader is `energy-source-r1` / `5807da6`; `energy-bounds-r1.json`
reuses the activity receipt by SHA and charges common physical power through
drain while EDP uses output latency. No raw/native re-execution. Its final five
targeted checks are in `logs/energy-final-tests.log`; `energy_bounds.json` is the
authoritative sensitivity receipt. Public anchors do not establish calibrated
pJ coefficients; ranges/residuals remain explicit.
Keep Fetch Controller, Fragmentation, new mapping and topology changes deferred.

## Interactive compute finding

The small [interactive-prefix gate](reports/INTERACTIVE_COMPUTE_REPORT.md) at
`3c641f0` passes 24 same-policy native workers; readbacks at `c4b3e0e`/`44f95e1`
preserve all physical events, commands, endpoint fingerprints and drain. Two
stable-case service intervals consume a committed partial prefix while remaining
data still returns. Weight arithmetic updates fall 16,384 → 4, but host
iterations stay 22,215 and native advancement is unchanged. Full worker is
slightly slower; Compact is about 1.11× faster through reduced output, with no
execution speedup. The matched quiescent Full remains about 1.36× faster.
Keep the candidate default off; do not present this as full-system acceleration
or FFN/placement evidence. Fifty execution-source tests and overlapping targeted
rechecks, plus 11 saved-evidence negatives, pass. Raw frozen source, tests and
captures stay in `/Projects/haoning/w2w-full-system-interactive-epoch-20261010`.
The next material performance opportunity needs certified component event
boundaries/interruptible service, not further tuning of this local rule.

## Causal boundary finding

The [boundary census and minimal P1](reports/CAUSAL_BOUNDARY_REPORT.md) executes
at `4daf6e4` with independent readback `d987cf0`. Sixty tests and 15 native
workers preserve physical events, command/endpoint fingerprints and drain,
including ordinary-path equivalence to the old accepted stable/transport runs.
Stable has 18,665 of 22,215 wakes without observed interface or projected
resource change, but that projection does not certify safe lookahead. All three
cases have zero certified active-array intervals; iterations and wall time do
not improve. The first-callback primitive alone cannot bypass pending atom
admission, finite Gateway output and NoC feedback. Keep the coordinator default
off; the verdict explicitly separates evidence success from acceleration
failure. Compact receipts are in `artifacts/provenance/causal_boundary`; raw
diagnostics and all failed attempts remain in
`/Projects/haoning/w2w-full-system-causal-boundary-20261010`. Select a qualified
eligibility or joint frontend/Gateway boundary before extending this route;
no P2, application matrix, or new speedup claim is authorized by this receipt.

## Native memory-service finding

The restricted [Domain Frontend/Gateway island](reports/MEMORY_SERVICE_ISLAND_REPORT.md)
at `3e2b12b`, read back by `6caeddd`, preserves the one-domain fixture's physical
records, finite reservations, commands, endpoint timing and drain across 36
native workers. Sixty-six execution-source regressions, one reader identity
regression and seven saved-evidence negatives pass. Array/refresh service is
unchanged. Host wakes drop about 20%, including active return/response overlap;
all NoC clocks and pending external descriptor-admission boundaries remain.
Worker benefit is near 1.00× in continuous/inserted cases and about 1.05× in the
finite-return-pressure fixture; increasing continuous data to 64 KiB does not
increase relative benefit. This is exact restricted joint service and modest
coordination reduction, not a large system acceleration. Keep it opt-in; no full
FFN, general multi-domain replacement or second island was run. Next work needs
an active NoC/system input contract to go beyond the retained 1 ns driver, with
measured cost evidence before expansion. Compact receipts are in
`artifacts/provenance/memory_service_island`, raw attempts/builds in
`/Projects/haoning/w2w-full-system-memory-island-20261010`.

## Domain-aligned organization gate

Latest steering changes the hardware question from placement/parameter tuning
to Domain → local logic/FIFO/cache ownership. See
[DOMAIN_ALIGNED_ORGANIZATION_REPORT](reports/DOMAIN_ALIGNED_ORGANIZATION_REPORT.md).
`domain_compute.py` refuses compilation: it conserves 65,536 PEs, 3 GiB SRAM,
2.875 GiB weight storage, 16,384 data/1,024 control HB signals, and shared matrix
issue budgets across 128 proposed domain tiles. Control serialization, scale
sharing/padding, landing footprint and local wire costs remain explicit.

Do not mistake sixteen aggregate simulator clusters for Cerebras's physical
compute granularity. Before claiming a new hardware benefit, a 128-tile
resolution baseline must retain existing Gateway/collection/storage behavior.
Output-row slices finish together under uniform service; they do not imply
intermediate-pipeline readiness. Whole-H Down prefetch needs 64 KiB/tile if it
waits for H. Proportional C/8 and W/8 cache slicing is not capacity pooling.

Source `8d531a9` passes six directed hn072 tests, including synthetic finite
E4M3FN/BF16 row equivalence and a real native Down-prefetch-before-H case.
The two cold full-size runs are frozen under
`/Projects/haoning/w2w-full-system-domain-organization-20261011/cold-r1`:
default Up-local and one bounded waiting Down per cluster using an existing
spare coupled fetch slot. Original compute edges, full SRAM storage, real
Native/NoC returns, two shared contexts/slots, and refresh/control stay intact;
8 B/cluster association is paid. The policy is cold-only, not a new cache run.
Default complete physical records must equal frozen `02dab2a` Up-local, and
the intervention must preserve native address/byte/resource work. Both full
cold runs and initial independent readback pass: **451.676 → 452.303 µs**,
a retained 0.1388% regression. Default equals the complete old Up-local physical
record; native bytes and NoC byte-distance stay identical. Twenty-eight Down
tasks start fetch before H, with 4,179,456 B committed early. Final Down's
release-to-completion interval shrinks 21.822 → 0.036 µs, but H release becomes
22.413 µs later, leaving layer completion 0.627 µs later. The same-capture
stage reader at `0c8f9e0` and final lifecycle reader at `2f1e4c1` pass. Its two
directed tests are rechecked. Four specification tests at `53b66a7` also pass,
and the complete default proposal/full-catalog digest matches the frozen image;
no additional full-size native execution.
Do not infer 128-tile performance or PPA from its bounds. In particular, equal
tag counts give 64 slice entries/domain, roughly 4 MiB effective capacity;
512 independent tags/tile would increase metadata eightfold. Resolve shared
directory/validity semantics before any cache timing claim.
Raw catalog, captures and worktrees stay outside Git; compact registration,
proposal and launch/test receipts are in `artifacts/provenance/domain_organization`.
No automatic retries or performance-based rejection.

## Vertical delivery and complete captured MoE continuation

The [vertical-delivery screen](reports/VERTICAL_DELIVERY_NECESSITY_REPORT.md)
at `3233bb3` reuses hashed completed cold, repeated Up-local and Down-prefetch
records. Descriptor-readiness committed-miss FIFO lower bounds are 64 KiB and
516 KiB per cluster; a 64 B direct FIFO needs a different word-level protocol.
Shared Gateway bypass can also save first-use reads. The repeated miss FP8 upper
bound is 2,017,460,224 B of 7,247,757,312 B read activity (27.84%). A collective
directory can preserve 367 matrices with paid slice flags/slot padding;
independent proportional tags cannot. Collection removal is a possible physical
benefit, conditional on paid local transport and uncalibrated residual costs.
No 128-tile timing, independent cache traffic, PPA or energy is established.

User explicitly requires complete real MoE traces, not repeated FFN smoke
fixtures. Source `3233bb3` restores all 256 authorized Qwen3 captures from
`/Projects/haoning/w2w-trace-20261007/memory_results/pbc_corpus256`:
94 layers, 10,460 prefill tokens, 32,768 decode tokens, 32,507,456 ranked
assignments. All raw entries are compared independently; no layer/token omitted
or reused. [CAPTURED_MOE_TRACE_REPORT](reports/CAPTURED_MOE_TRACE_REPORT.md) and
`artifacts/provenance/captured_moe` keep source/model/capture hashes and coverage.
Data/model config pins are distinct and neither contains credentials. The
capture lacks logits/probabilities/activation values and hardware timings.

Frozen `source-r3` / `a708d50` prepares the long post-router MoE pair under
`/Projects/haoning/w2w-full-system-vertical-delivery-20261011/full-request-r2`.
It covers the first original manifest request, true layers 0/1, all 46 prefill
and 128 decode tokens, 258 invocations, explicit dispatch/expert/combine and
empty finite SRAM cache. The two cases retain Phase-Split weights with Reference
versus Up-local compute. No smaller shape, route truncation or copied layer.
The serial controller/auditor are in the repo, Native tools are the accepted
frozen binaries, and no automatic retries/performance rejection are permitted.
Check `pipeline-status-r2.json`, `full-request-r2/controller-status.json` and
case logs before claiming completion. This is not 94-layer Transformer timing.

The first preparation (`full-request-r1`, source `2b01f4c`) failed on a task-field
name before Native execution; retained log is `logs/full-request-prepare-r1.log`.
`a708d50` fixes it and includes registration in the directed regression. Keep the
failed directory/log and the complete-corpus frozen image; do not reset worktrees.
Complete 94-layer expert weights alone require 211.552 GiB, exceeding 8 GiB;
reject unsupported full-model execution rather than shrinking/reusing weights.

## Real MoE / executable NPU G1–G5 continuation

See [REAL_MOE_NPU_GATES_REPORT](reports/REAL_MOE_NPU_GATES_REPORT.md) and
`artifacts/provenance/real_npu/accepted-qualification-r19.json` (historical
foundation-r11 is retained). User requests
complete real traces and G1–G5; do not substitute FFN smoke or treat launch as
acceptance. All 256 captures/94 layers are analyzed; actual expert M/ranks,
modeled Router visibility, pack/scatter/combine and finite shape-aware OS NPU
are implemented. Independent 36-shape SCALE-Sim/full-size physical gates,
FP8/BF16 cold-to-warm boundaries, 32 BF16/GQA shapes and mixed vector/array
event equivalence pass. Source-r19 passes 26 directed hn072 regressions, actual
mapped increasing-K numerical checks, final cumulative Native ID/pressure
reconciliation, and the certified idle/fixed NPU epoch physical equivalence.
Vector output storage is reserved before execution; ordered K partial additions
are separately charged. The complete-weight OS and vector service models are
declared conservative references, not calibrated silicon or optimal dataflows.

Remote root is `/Projects/haoning/w2w-full-system-real-npu-20261011`.
Corrected campaign source `c820e25` is frozen as `source-r20`; qualified
execution source is `source-r19@e4ae2b8`. Controller `campaign-r20` PID 823775
waits for `resources-r19` (PID 823535) and `context-r19` (PID 823537). Each exercises the
first two real prefill tokens at full H/I in true layers 0/1. They qualify
resources only, not complete requests. Check receipts/process identity before
reuse. `resources-r10` failed final observation-ID reconciliation;
`context-r11` exceeded a directed 5 ms budget; `campaign-r12` failed its
prerequisite without launching applications. r16 resource/context runs were
invalidated for K-reduction/vector storage corrections. Keep all evidence;
none of those is accepted application timing. `study-r8@2c83290` was invalidated before its first completed window:
legacy vector service had omitted SRAM/partial/conversion work. Preserve its
invalidation/prior status and all failed launch logs. Original frozen
`full-request-r2@a708d50` is untouched; it uses the older aggregate model.

`tools/run_npu_gates.py` requires accepted receipts and current readback before
launching all complete B1/4/16/32 × three-mapping G3 cases. Full original prefill
plus 128 decode steps run with real distinct layers and continuous physical
Native/NoC/LRU state; lossless window archives retain complete events. It later
launches conditional 94-layer G4 only after complete B1 Up-local acceptance.
G4 explicitly provisions 47 four-reticle V3 stack copies, true GQA/KV, modeled
missing inputs/arrivals, finite paid links and request lifecycle. No unsupported
single-stack full-model capacity or real numerical text claim. It has at most
two active physical/reader workers. G5 refuses final figures without complete
accepted G3/G4. Keep the goal active until required readbacks and final decision
finish; pending qualification/background jobs are not completed gates.

## Limits (historical comparisons)

No search/DSE, new fanout/endpoint RTL, partitioning rewrite, thermal/yield
project or additional hardware is required by the completed comparison.
Optimized central fanout, fair external I/O cost, prefill and a complete
Transformer remain unmeasured. The historical two-layer study reuses archived routing at
the second layer and excludes attention/KV/norm/residual/numerical execution.
Ideal global RX booking, aggregate SRAM banking and assumed array timing remain
explicit. Do not promote these resource proxies to product-calibrated PPA.
