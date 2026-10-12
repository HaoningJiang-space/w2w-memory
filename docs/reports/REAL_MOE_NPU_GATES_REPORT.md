# Real MoE → executable WoW NPU: evidence and remaining gates

The accepted foundation now executes actual expert token shapes on a concrete,
finite NPU array model. **G3 has its first accepted complete B1 Reference case;
the twelve-case G3 campaign and G4/G5 remain incomplete.** No smaller FFN,
truncated request or registered background job counts as acceptance.

## Frozen workload and completed foundation

The existing corpus is reused without recollection: 256 independent requests,
all 94 layers, 10,460 prefill tokens, 32,768 decode tokens and 32,507,456 ranked
token–expert assignments. The dataset revision remains
`27febb7b2d24169560a9f6f83d38eb53f94916cf`. The model-config pin is distinct from
the capture identity; the capture does not identify its producing checkpoint
revision or contain numerical activations, probabilities, vocabulary IDs,
logits, request arrivals or hardware timings.

[Historical compact foundation](../../artifacts/provenance/real_npu/accepted-foundation-r11.json)
binds the original full receipts, source commits, native results and regression
logs by SHA256. Raw captures and physical event archives remain outside Git.
The [current qualification receipt](../../artifacts/provenance/real_npu/accepted-qualification-r19.json)
binds the corrected execution source `e4ae2b8`, 26 passed regressions, renewed
shape/numerical references and current physical boundary/equivalence checks.
All 36 full projection programs match the earlier reference exactly, allowing
their compute-resident and Native-streaming results to remain applicable.

G1 groups the original ranked selections into expert work items with actual
`M=n_e`, preserving request/token/layer identity and `sum(n_e)=8B`. Pack,
dispatch, scatter and ordered weighted combine are explicit tasks and edges.
The modeled BF16 router matmul and top-k normalization finish before any
captured expert selection becomes hardware-visible. The full 128-expert catalog
is independent of the evaluated selections; the two layer catalogs have distinct
storage identities and physical addresses.

The demand reader covers every captured decode layer/step and every request,
using disjoint source-order cohorts. These aggregate results need not equal an
earlier single-layer or differently grouped batch statistic:

| B | Mean active experts | Active-expert n_e P99 |
|---:|---:|---:|
| 1 | 8.000 | 1 |
| 4 | 24.297 | 4 |
| 16 | 54.746 | 11 |
| 32 | 70.882 | 20 |
| 64 | 92.197 | 28 |
| 128 | 111.172 | 37 |

![Full captured demand](figures/real_npu/fig1-real-demand.png)

G2 defines output-stationary arrays, finite operand ports, declared banking,
bounded broadcast, FP8 conversion/scale work, FP32 K-partial storage and ordered
reduction. Both 64×16×16 and 16×32×32 preserve the original 16,384 MAC/cycle
cluster budget; the two compute contexts, two fetch slots, SRAM capacity,
requester window, Native DRAM and BookSim remain shared and finite. Arrays
acquire a nonpreemptive group only after the full operands are committed. This
is a conservative executable reference, **not an optimal GEMV/weight-stationary
mapping or a calibrated chip**.
For partitioned K, the original complete dot product is formed before SiLU:
the first partial is loaded into the already paid array accumulator registers,
each later partial performs a separate addition in increasing K order, and the
final output is stored only after the last addition. Vector output storage is
reserved before execution. Outgoing DataEdges already own source SRAM at task
admission; ordered vector phases can reuse those not-yet-visible buffers.
Only temporary output beyond that capacity adds scratch. Incoming buffers remain
separately owned, and delayed stores cannot borrow unowned SRAM.
The vector phase model is a conservative resource reservation model, not a
silicon-calibrated vector ISA or cycle-accurate RTL pipeline.

Independent SCALE-Sim OS demand schedules at pinned commit
`f79d7bc39a80a21fc35bc667967b76a15b311f49` match all 36 full H=4096/I=1536
projection shapes: M=1/2/4/8/16/32, Gate/Up/Down, both array organizations.
Synthetic finite E4M3FN, original 128×128 scales, BF16 activation and ordered
FP32 FFN checks pass. Separately, 36 compute-resident and 36 true Native-streaming
physical microkernels pass, as do FP8/BF16 cold→warm continuous-cache boundaries.
Those tests qualify the kernel interface; they are not real-application timing.

![Array shape reference](figures/real_npu/fig2-shape-efficiency.png)

The added mixed array/vector equivalence case has 6,292,992 B actual Native
traffic. Cycle and epoch evidence both finish at 264,350,000 ps, with every
noninternal physical event and resource record equal. Only the known archive
path is normalized in the otherwise identical BookSim config; topology and
binary identities remain checked. Native/NoC clocks are not skipped.

The independent BF16/GQA reference covers 32 small/tail K shapes, including
unequal word-aligned K partitions. Separate per-head NumPy attention matches
the actual array tile mapping and increasing-K partial reductions in the
grouped 16-query-head-per-KV-head layout, causal mask, V transpose and zero
padding for lengths 1/2/46/174 (maximum synthetic absolute error 0.0001220703125).
These are synthetic numerical checks, not captured Qwen tensor inference.

## Resource correction before G3

The initial `study-r8` registration at `2c83290` was stopped before its first
completed window. Inspection found that legacy vector stages lacked explicit
internal SRAM copy/partial/conversion service. Its invalidation and prior
controller status are retained on hn072; it supplies no accepted G3 result.
The unrelated frozen aggregate-streaming `full-request-r2@a708d50` continues
unchanged and cannot be promoted to the new NPU model.

The replacement pays materialized input copies, pack's 24 block consumers,
SiLU-product service, ordered block/partition accumulation, FP32→BF16 output,
ranked weighted combine, finite coefficient broadcast and their scratch storage.
An independent mathematical/ownership reader checks these against actual
captured memberships rather than only the final makespan. BF16 router weights
use the same ordinary finite matrix cache and tag/lookup budget.

Later qualifications remain archived as failures or invalidations, rather than
accepted application results. `resources-r10` archived two real-token windows
but failed final Native source-pressure reconciliation because an observational
packet-ID map was retired too early. That map now persists across windows;
the renewed remote cold→warm boundary verifies final cumulative Native pressure.
`context-r11` exceeded its directed 5 ms simulation limit; the full-shape Q/O
traffic is not a smoke-sized workload, and the replacement allows 50 ms.
`resources-r16` and `context-r16` were stopped before acceptance to correct
K-reduction dependencies and vector output ownership. No failed record is
silently repaired or used as a completed-request result.

## Complete campaigns and acceptance

`tools/run_npu_gates.py` is a one-shot, no-retry controller. It first requires
passed shape, compute, Native, continuous-state, mixed-event equivalence and
real-token resource receipts. It re-reads the latter archives under the current
auditor before starting the complete G3 study.

G3 registers B=1/4/16/32 × Reference/Phase-Split/Up-local. Nested cohorts select
the first four source-order requests from each of eight subjects before seeing
performance, then retain original manifest order. Every selected request runs
all captured prefill tokens and all 128 decode steps, with two **different real
adjacent layers 0/1**, full shapes and catalogs. Prefill has bounded 32-token
microbatches; no captured token is dropped. One physical case runs at a time.

Windows retire only after physical drain. Native row/refresh/controller state,
BookSim routers/credit/arbitration, DMA availability, clocks and cache LRU
persist. Complete window evidence is losslessly column-encoded, retaining
every event, key, value and order; each archive binds both file and decoded
canonical hashes. This is evidence compression, not hardware approximation.
Offline readers independently recheck every window and its carry chain.

G4 extends the same kernel with full-shape Q/K/V/O, per-head RMSNorm/RoPE,
grouped causal GQA, paid softmax/BF16 conversion, residuals, BF16 KV append/read,
embedding lookup and a full untied BF16 LM head with ordered max/index combine.
KV uses reserved existing non-cache SRAM; it cannot silently shrink the 184 MiB
weight cache or truncate context. The declared 256-token/request KV limit is a
hardware assumption; unsupported requests are rejected.

The 94-layer capacity plan uses **47 copies of the four-reticle V3 stack**, each
with its own independent two-layer residency, Native resources, cache and clock.
This is not 47 full 300 mm wafers and not one 8 GiB machine. Point-to-point
activation and token-feedback links have finite ports, packet/header/cell work,
latency and buffers charged to existing SRAM; real c15 ingress/export edges
pay local NoC transport. Transfers wait for quiescent endpoint windows, and
output state remains owned until transmission completes.

The existing boundary driver can advance only a certified idle interval or an
already admitted nonpreemptive fixed NPU epoch. The latter has committed
operands, a fixed cursor and no scalar/dynamic competitor. Native DRAM still
executes every internal clock/refresh, and active NoC/DRAM feedback is never
skipped. A renewed full-projection equivalence case with a known 500 µs idle
release has identical 764,355,000 ps timing and physical records. Its ordinary
and certified-boundary host times were 25.329 s and 16.975 s respectively;
this directed timing is not a promised full-application speedup.

All request arrivals are explicitly modeled at zero. Captured prefill row count
is the declared context-length assumption. Missing vocabulary IDs use a named
stable modeled address policy, never presented as real IDs. Only a completed
47-stage trace-driven replay may emit conditional TTFT/TPOT for the captured
129-emission horizon. Numerical text generation, true EOS, silicon timing and
calibrated energy/area remain outside that claim.

G4 starts only after the context/KV resource gate and the complete accepted
G3 B1 Up-local case. At most two G4 physical/archive-reader workers hold active
slots; other stages wait. G5 final figures reject incomplete G3 or G4 evidence.
Its decision must distinguish resource work bounds from recoverable stalls and
conditional EDP inequalities from measured total energy. No new hardware is
justified merely by a layout, low modeled utilization or an uncalibrated energy
coefficient. A negative architecture decision is retained if a costed mechanism
has not beaten the strongest legal baseline.

## Status to check before claiming completion

hn072 root: `/Projects/haoning/w2w-full-system-real-npu-20261011`.
The latest executable
campaign source is `a69d29e` (`source-r27`). Executable and read-only analysis
snapshots are immutable detached Git worktrees. Check the
[complete campaign launch](../../artifacts/provenance/real_npu/campaign-launch-r27.json)
and campaign status
rather than assuming a finished gate from this report.

Controller PID 826834 launched G3 controller 826982 and first physical worker
826983 (`B1-reference`). The full study root is `campaign-r27/real-moe`;
conditional full context is `campaign-r27/full-llm-B1`. PIDs are historical
launch evidence; verify current command identity before operating on them.
The [recorded status](../../artifacts/provenance/real_npu/campaign-status-r27.json)
is the historical pre-completion snapshot. The later B1 result is recorded below.
The obsolete `campaign-r12` failed its prerequisite
without applications; `campaign-r20` was invalidated before application launch
when compiler inspection found duplicate output storage charging.

The ownership correction passes [27 directed regressions](../../artifacts/provenance/real_npu/regression-r25.json)
and [24 real-route compiler views](../../artifacts/provenance/real_npu/mapping-preflight-r26.json).
The latter covers each B and mapping's first actual prefill plus its largest
actual decode expert M. Largest observed M in the B32 cohort is 27: Pack needs
5,529,600 B, below the 8,379,816 B intrinsic non-cache budget. The synthetic
maximum-M32 capacity guard needs 6,553,600 B. Counting the outgoing payload twice
would instead require 12,845,056 B at M32 and incorrectly block admission.
No tokens are removed and no SRAM/cache budget is enlarged. Intrinsic capacity
is a necessary check; dynamic peak and progress still require complete execution.

Both earlier real-token physical qualifications now have passed final receipts:
[MoE](../../artifacts/provenance/real_npu/real-token-resource-r19.json) has two
continuous windows, 2,064 tasks, 568,466,432 B Native traffic and 606,076,928 MACs;
[Attention/KV](../../artifacts/provenance/real_npu/real-context-resource-r19.json)
has 2,244 tasks, 711,179,264 B and 891,387,904 MACs. The additional 285,310,976
MACs equal four full Q/K/V/O invocation sets plus grouped QK/AV for context lengths
1 and 2 in both layers. Actual append/read events preserve contiguous KV history.
These remain the first two actual prefill tokens, not complete requests.
Their older declared extra scratch stays charged in the archived graphs; current
readers independently re-audit those legal over-reserved graphs before reuse.
They do not establish identical lowering or new application performance.

- G1: full-corpus identity/grouping/demand checks accepted.
- G2: shape/core, full-size physical microkernels and carry/equivalence accepted;
  banking/ports/dataflow remain explicit uncalibrated assumptions.
- G3: B1 Reference complete and independently accepted; Phase-Split running,
  remaining registered cases pending.
- G4: implemented and independently shape/numerically qualified; awaiting
  full 94-layer serving acceptance after complete B1 Up-local and current context readback.
- G5: evidence-bound analysis implemented; final decision awaits completed runs.

Two design limits prevent overstating the hardware conclusion: the NPU reference
has a complete-operand OS barrier and does not establish the best possible
row-streaming/weight-stationary baseline; the initial G4 attention projection
placement is legal but is not a demonstrated optimal output-channel mapping.
Before claiming new hardware, those software alternatives and calibrated
physical costs must be compared. A completed negative design screen is not
evidence that a new structure exceeds the strongest legal baseline.

No background registration or directed qualification is labeled a completed
application result. Failures are retained, not retried automatically.

## Stronger software baseline and architecture acceptance

The [multi-wave K mapping reference](../../artifacts/provenance/real_npu/mapping-reference-r30b.json)
qualifies an optional mapping on the same 64×16×16 arrays, ports and SRAM. It
does not change the default programs or the frozen `source-r27` campaign.
All 36 prior full projection programs are rechecked against the explicitly
loaded, pinned primary SCALE-Sim module, including array cycles and weight reads.
The recorded module path and SHA256 prevent an unrelated installed copy from
being used as the independent reference.

| Full Gate shape | Default service cycles | Two K partitions: service cycles | Declared scratch |
|---|---:|---:|---:|
| M=1, N=1536, K=4096 | 8,255 | 6,241 | 145,408 B |
| M=4, N=1536, K=4096 | 8,255 | 6,242 | 182,272 B |
| M=8, N=1536, K=4096 | 8,255 | 6,245 | 231,424 B |

Cuts preserve the original 128-wide FP8 scale boundaries. Partial outputs and
ordered reduction retain finite, paid storage and service. Synthetic full-shape
numerical checks pass; they are not captured Qwen tensor checks. These are
standalone kernel service improvements, not application speedups, an optimal
mapper or new hardware evidence. Earlier r28/r30 reference launches failed on
import/dependency paths and remain unaccepted; the isolated corrected r30b
launch passed without changing Native tools or shared environments.

The G5 reader now distinguishes a completed twelve-case **mapping screen** from
architecture acceptance. It checks identical trace/cohort/layer/kernel work,
rejects missing, duplicate or incomplete cases, and ranks the observed
latency/activity Pareto points. Ranking those unchanged-hardware mappings cannot
alone establish a structural hardware contribution. Acceptance still needs a
completed structural intervention, the strongest legal software baseline and
explicit physical cost bounds. Missing evidence is not proof that new hardware
has no value. [Eight directed regressions](../../artifacts/provenance/real_npu/regression-r31.json)
cover mapping boundaries and this evidence contract; their reader fixtures are
deliberately fictitious and are not application results.

The running `source-r27` controller remains frozen with its older final-status
writer. If it eventually prints G5 complete, re-read its results using the current
architecture criteria before claiming goal completion. Its terminal label alone
does not satisfy the structural/cost gate.

## Full-serving completion binding

The current G4 reader also checks the serving chain across physical stages.
Every notice must match the corresponding accepted raw-window SHA256, decoded
identity, makespan/drain, captured token IDs, heads and effective input release.
The effective release includes both the paid input ticket and the previous
output buffer's transmission fence. Accepted stage proofs must cover their own
actual layers, the complete cohort assignments, all KV histories and the full
output horizon. All retained raw-window hashes and prerequisite receipts are
checked again. Stage-zero prompt releases and later autoregressive releases
must refer to the actual preceding transfer/feedback; an invented future-token
ticket is rejected.

[Seven directed context/lifecycle regressions](../../artifacts/provenance/real_npu/regression-r33.json)
pass on hn072. They reject invalid phases, negative/out-of-horizon decode steps,
early output release and mismatched notices. This verifies the reader contract,
not complete 94-layer execution.

A [separate read-only observer](../../artifacts/provenance/real_npu/postrun-readback-launch-r34.json)
is frozen at `analysis-r34@d1d43f3`, PID 832174, under
`postrun-readback-r34`. It verifies the specific live campaign controller 826834,
waits for complete G4 acceptance, runs the current full-serving readback, and
generates final figures only after all twelve complete G3 cases are accepted.
It changes no physical job or frozen source and never retries an experiment.
Incomplete status-file writes during a live poll are observations to recheck,
not terminal failures. Its own final status still distinguishes mapping-screen
completion from unproven architecture acceptance.

## Complete captured GQA shape horizon

[The trace-bound GQA reference](../../artifacts/provenance/real_npu/trace-gqa-reference-r36.json)
uses the exact registered B1 cohort/config hashes and the original request
hash. Its 46 prefill tokens produce a 32-token window and a 14-token tail;
all 128 decode steps then extend KV from length 47 through 174. All 130 distinct
query/KV shapes are checked against the explicitly loaded pinned SCALE-Sim
module and separate per-head NumPy attention. The largest grouped query M is
512, and the tail M is 224 (16 query heads per KV head). No query token or
history position is omitted. Synthetic BF16 values have maximum absolute
error 0.00006103515625; the capture still supplies no numerical tensor values.

| Actual prefill query rows | KV length | Kernel | Array-core cycles | Modeled bank stalls | Total service cycles |
|---:|---:|---|---:|---:|---:|
| 32 | 32 | QK | 158 | 384 | 544 |
| 32 | 32 | AV | 248 | 0 | 256 |
| 14 | 46 | QK | 158 | 128 | 288 |
| 14 | 46 | AV | 152 | 0 | 156 |

Array-core comparisons do not calibrate the declared SRAM banks. The separate
bank/service columns expose the modeled cost of operand delivery; they are not
measured stalls in a completed 94-layer request. Original smaller numerical
cases remain valid, but they alone did not exercise the complete 32/14-token
prefill grouping. The renewed reference changes no frozen application program,
Native timing, routing or physical resource budget. It qualifies the computation
interface for the full captured horizon, not G4 serving latency or G5 hardware.

## Read-only competition diagnosis

`tools/analyze_npu_competition.py` supports explicit array cycles and fixed
epochs, decoding the complete lossless event archive before re-auditing it.
It reconstructs dependency eligibility, admission, complete operands, context
start, first arithmetic grant and completion. Its per-task intervals partition
that task's span; sums across tasks still overlap and are not application stalls.
Context area and shared arithmetic service must match the execution ledgers.

The [first actual-token window readback](../../artifacts/provenance/real_npu/npu-competition-window0-r23.json)
is bound to its raw archive hash and analysis source `f629a39`. This is a
directed qualification window in real layers 0/1, not a completed request.
Its last Down (`L1/e55/b11/down`) spends 21.320 µs from admission to complete
operands and 0.637 µs in array service, with no context-start or first-grant wait.
During its 17.347 µs descriptor issue span, the MC pool is full for 17.233 µs.
The disjoint *slot-time* composition of that full interval is 53.43% before
first atom admission, 41.31% during atom admission, 2.17% from final admission
to final array callback, 2.91% from callback to final Gateway payload and 0%
from final payload to MC release (the remaining 0.17% precedes vertical
admission). Those phases include finite frontend/controller/refresh feedback;
they do not uniquely isolate DRAM latency or establish a recoverable speedup.
The result provides a concrete supply-side diagnostic to repeat on the completed
warm and grouped cases, rather than attributing a full MC pool to one component.

## First complete captured-request result and observed transition

[The complete B1 Reference receipt](../../artifacts/provenance/real_npu/B1-reference-complete-r40.json)
binds the independently audited `source-r27` result, completion, cohort and
registration by SHA256. It executes all **46 captured prefill tokens and 128
decode steps in real layers 0/1**, with continuous Native/NoC/cache state:
130 windows, 152,302 tasks, 2,784 token–expert assignments and 52,728,692,736
matrix MACs. Completion is **48.948846 ms**; physical drain is 48.948886 ms.
Native reads are **7,845,262,592 B**, including **3,765,306,624 B reload**.
This is complete captured lifecycle evidence for a two-layer MoE window, not
94-layer Transformer TTFT/TPOT. The other eleven comparisons remain required.

The [source-bound transition plot](../../artifacts/provenance/real_npu/B1-transition-r41.json)
uses every original decode step. It reuses the accepted raw-event audit and
checks its source bindings; drawing the plot is not a second full raw-event
audit. Service bounds overlap and must not be summed as stalls.

| Observed decode group | Windows | Median two-layer completion | Largest necessary work bound |
|---|---:|---:|---|
| Zero Native weight reads | 51 | 50.173 µs | Shared NPU service, all 51 windows |
| At least one Native weight read | 77 | 235.882 µs | Assigned Gateway payload in 76 windows; shared NPU service in one |

![Complete B1 decode transition](figures/real_npu/B1-decode-transition-r41.png)

For original decode step 0, completion is 51.464 µs, with a 36.827 µs shared
NPU work bound and zero Native bytes. At step 2, completion is 232.325 µs,
with 23,074,304 B Native reads, a 147.492 µs assigned-Gateway payload bound
and a 31.589 µs shared NPU bound. These observed windows motivate separate
resident and cold-supply studies. They do not isolate a recoverable stall or
prove an optimal dataflow. Aggregate useful MACs divided by reserved NPU
service capacity are 6.517%; this is modeled service utilization, not measured
silicon utilization or an application-wide duty cycle.

The optional output-channel Q/K/V/O mapping added after the frozen campaign
preserves full hidden reductions and original 128×128 scale identities.
Copies use a finite four-way tree; descriptor initialization/read service and
FP32 row gather are charged to existing SRAM/ports. It is a stronger legal
software baseline candidate, not new hardware or an accepted application
speedup. The default campaign programs remain frozen.

[Sixteen directed regressions](../../artifacts/provenance/real_npu/regression-r40.json)
pass at `5f38270` on hn072. Projection audit now traces each copy/shard to the
correct normalized BF16 input or Attention head concat, requires a complete
original weight read, rejects duplicate assemblies/extra Gather inputs, and
checks descriptor initialization precedes dependent copy/gather work.
Same-byte wrong tensors, reordered phases, omitted copy nodes and precision
changes are tested as rejection cases. Compiler and Native qualification of
the candidate remain separate from these reader tests.

[Actual B1 compiler preflight](../../artifacts/provenance/real_npu/projection-preflight-r40.json)
passes the first/tail prefill and first/last decode in both real layers
(eight views per policy). Default graphs, kernel identities, metadata and
catalog match `abf28d6` exactly. The candidate's nine distinct projection-shard
shapes match the pinned SCALE-Sim array core, with at least 5,627,048 B
intrinsic non-cache SRAM headroom after the unchanged cache, KV and endpoint
reservations. Intrinsic headroom does not establish dynamic progress.

[Native qualification launch](../../artifacts/provenance/real_npu/context-output-sharded-launch-r40.json)
starts one isolated two-token context resource gate at `analysis-r40@5f38270`,
PID 889899, using the same accepted Native binaries. Verify its current
identity, `context-output-sharded-r40/receipt.json` and its retained log before
accepting it. Launch is not completion; no retry or change to the r27 campaign
is authorized by the launch receipt.

Separate selected-window raw readbacks at `analysis-r42@39e091e` pass for
[decode step 0](../../artifacts/provenance/real_npu/B1-decode-0-competition-r42.json)
and [step 2](../../artifacts/provenance/real_npu/B1-decode-2-competition-r42.json).
They preserve prior raw hashes, physical/request/NPU audits, context ledgers
and projection tails. Step 2's final twelve projections are cache hits, so
the reader now searches the complete projection list for the last Native-read
projection. It finds `L0/e1/b11/down`: a 17.843 µs descriptor issue span
intersects a full MC pool for 17.729 µs. The final cached projection still
executes a paid 0.637 µs array service. Thus a cached completion tail does
not establish absence of earlier supply delay; these intersections still do
not identify recoverable application latency. The earlier r41 readbacks are
retained as the pre-correction reader evidence.
