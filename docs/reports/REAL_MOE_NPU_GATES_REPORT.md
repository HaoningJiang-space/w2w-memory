# Real MoE → executable WoW NPU: evidence and remaining gates

The accepted foundation now executes actual expert token shapes on a concrete,
finite NPU array model. G3–G5 are **not completed application results**. Their
complete captured-request campaigns are gated on resource qualification; no
smaller FFN, truncated request or registered background job counts as acceptance.

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
has no completed G3 case yet. The obsolete `campaign-r12` failed its prerequisite
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
- G3: complete registered physical campaign running; no accepted complete case yet.
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
