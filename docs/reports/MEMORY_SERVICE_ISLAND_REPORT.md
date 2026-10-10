# Memory service island: exact joint service, limited system benefit

The restricted native Domain Frontend/Gateway works. It preserves the original
service and feedback while reducing host wakeups by about **20%**, including
intervals with ongoing array returns and supplied NoC responses. It does **not**
establish substantial system acceleration: most workers are near 1.00×, the
finite-return-pressure fixture is about **1.05×**, and increasing the continuous
stream from 8 to 64 KiB does not increase the relative gain.

Execution source: `3e2b12b`; native build: `b8ee940`; independent reader:
`6caeddd`. Raw records and all development attempts stay on hn072 in
`/Projects/haoning/w2w-full-system-memory-island-20261010`. The accepted run is
`gate-003`; no FFN, placement matrix, G2.2/G2.3 or second island was run.

[Protocol](MEMORY_SERVICE_ISLAND_PROTOCOL.md) ·
[checked worker results](../../artifacts/provenance/memory_service_island/VERIFIED.json) ·
[separate research verdict](../../artifacts/provenance/memory_service_island/VERDICT.json) ·
[environment](../../artifacts/provenance/memory_service_island/ACCEPTED_ENVIRONMENT.json).

## Execution boundary and retained information

This first implementation supports exactly one physical RWDL domain, one owning
Gateway and one bank-group view. The small declared machine retains one paired
reticle's Compute Mesh and the original 128 B flit, 16 B header, 1 ns logic and
3.76 ns array clocks. It is a component-system fixture, not the full V3 machine.
Unsupported larger inventories fail explicitly.

Ramulator still performs all array ticks, command scheduling, rows and refresh.
The reviewed native island owns the original descriptor window/selection,
atomic request acceptance, finite return reservations, range/ACK protocol,
coordinate-derived collection, CDC and Gateway output. Same-cycle event order
remains callbacks → scheduled events → Gateway → atom issue. Scheduled events
retain insertion sequence. The old Python `VerticalRWDL` remains the independent
ordinary frontend reference.

The island knows its next required **internal** boundary: an array tick, a
queued frontend event or a nonempty Gateway's next service cycle. Before that
boundary it avoids empty native calls and empty logic phases. External submission
invalidates the certificate. It never guesses a future completion or omits an
array/refresh tick.

Standalone `advance_until(external_limit)` returns on first data, increased
flit supply eligibility, final descriptor completion, ACK capacity release or
the caller's known input cap. First data must remain observable before 112 B:
the current kernel attempts response NI admission on the first nonzero prefix.
Using only the first flit threshold would change finite NI reservation timing.
Final padding, prefix holes and descriptor ownership also remain explicit.

The **system integration is deliberately more conservative**. It retains every
NoC/compute clock and every DRAM boundary required by pending external descriptor
admission. Other array/frontend clocks execute inside the island. It does not
yet let the system wake solely on NI supply eligibility, and it does not run an
active BookSim network ahead of possible new system input. Full physical evidence
is retained; no compact-output speedup is used here.

## Fixed scenarios and accuracy

Continuous uses an 8 KiB weight stream. Inserted adds an independent consumer on
c2 at 752 ns while c3's service is underway. The pressure fixture declares two
return atoms and a 64-cycle Gateway access pipeline. It exercises reservations
held through transport; it is **not** evidence of multiple-input Gateway queue
contention. The long control changes only continuous weight length to 64 KiB.
Each ordinary/port-only/coordinated pair has identical hardware and workload;
capacities differ between the declared pressure and continuous fixtures.

**66 execution-source regressions pass**, plus the new independent-reader
identity regression. Standalone native checks reconstruct all timestamped atoms,
control records and finite resource totals and compare all Ramulator commands
and stats through 20 µs, including REF. Native service outputs are generated
independently, not supplied from the ordinary trace.

The final gate runs **36 workers**, three repetitions of all three modes for
three scenarios plus the continuous length control. Physical records, operand
readiness, task/resource clocks, command/time/address fingerprints, endpoint
mutation/progress/completion fingerprints and drain are identical. Readback
binds input/source/binary/result hashes and enforces the retained NoC clocks.
All **seven saved-native-evidence negatives** are rejected, including changed
first readiness, duplicate control events, altered reservation state, unknown
receipt fields, wrong update/tick totals and deletion of a NoC wakeup.

| Case | Ordinary / port-only host wakes | Coordinated host wakes | Omitted | Completion = drain |
|---|---:|---:|---:|---:|
| Continuous 8 KiB | 3,310 | 2,639 | 671 | 2.636 µs |
| Continuous 64 KiB | 26,878 | 21,425 | 5,453 | 21.410 µs |
| Return pressure | 45,446 | 36,205 | 9,241 | 36.202 µs |
| New consumer inserted | 6,813 | 5,431 | 1,382 | 5.426 µs |

Of the omitted clocks, respectively **542, 5,192, 8,845 and 1,231** lie in the
intersection of real first-to-last array-return intervals and first-supply-to-
delivery response intervals. This witnesses overlapping memory/network service;
it does not assert that a router grants a flit on every omitted clock.

| Coordinated case | Host memory advances | Native island advances | Internal frontend phases | Array ticks |
|---|---:|---:|---:|---:|
| Continuous 8 KiB | 2,639 | 1,613 | 2,284 | 701 |
| Continuous 64 KiB | 21,425 | 12,923 | 18,376 | 5,694 |
| Return pressure | 36,205 | 10,520 | 19,761 | 9,628 |
| Inserted | 5,431 | 3,262 | 4,644 | 1,443 |

The ordinary adapter already avoids a bridge advance when the array clock has
not changed. Therefore island-call counts must not be compared to ordinary host
wakes as a claimed reduction in C++ round trips. Internal array ticks are exactly
the same. The extra reduction in frontend phases skips only certified empty
logic service, not busy memory commands or finite-resource feedback.

## Measured costs

Same-batch medians without a profiler, three repetitions/mode, fixed affinity
18/19. A minimal wakeup-list observer is enabled identically in all modes for
independent clock readback; the execution times include that observer:

| Case | Ordinary worker | Coordinated worker | Worker ratio | Ordinary execution | Coordinated execution | Execution ratio |
|---|---:|---:|---:|---:|---:|---:|
| Continuous 8 KiB | 0.331 s | 0.332 s | 0.997× | 0.203 s | 0.200 s | 1.018× |
| Continuous 64 KiB | 1.636 s | 1.619 s | 1.011× | 1.491 s | 1.477 s | 1.010× |
| Return pressure | 2.201 s | 2.102 s | 1.047× | 2.063 s | 1.962 s | 1.052× |
| Inserted | 0.526 s | 0.518 s | 1.014× | 0.395 s | 0.389 s | 1.016× |

Ratios use unrounded medians. Initialization and output are included in worker
wall time; execution spans `execute_system` and backend close. Full event counts
and physical payload/protocol evidence are equal. Host peak RSS is 43,384 KiB
in these medians; it excludes BookSim's child RSS. No memory improvement is
claimed.

Execution timing excludes writing the wakeup-list JSON, but includes collecting
its entries. Near-1% differences are not established as an improvement in a
deployment without the observer. These results do not justify a larger timing
campaign or a claim that evidence generation alone was removed.

| Case | Host-process CPU, ordinary → coordinated | BookSim child CPU, ordinary → coordinated |
|---|---:|---:|
| Continuous 8 KiB | 0.182 → 0.181 s | 0.032 → 0.031 s |
| Continuous 64 KiB | 1.344 → 1.332 s | 0.245 → 0.240 s |
| Return pressure | 1.859 → 1.762 s | 0.349 → 0.348 s |
| Inserted | 0.356 → 0.354 s | 0.062 → 0.059 s |

The historical `python_cpu_seconds` field is process CPU and **includes the
synchronous native DRAM bridge**. It is not isolated Python CPU. These timings
cannot assign separate CPU shares to DRAM and Python/IPC, or be added to worker
wall time. The evidence establishes a small pressure-fixture gain, not a robust
large speedup across streaming inputs. The long control supplies no evidence of
improving relative gain with service length.

## Development attempts and scope of the result

`gate-001` ports the service but still calls the island at every host wake;
accuracy passes, and runtime worsens. `gate-002` adds known internal-boundary
certificates, giving a small pressure-fixture benefit. Both compact receipts are
published and all raw runs remain archived; the headline table uses only the
final registered batch rather than selecting the best earlier repetition.

An early component comparison wrongly compared command-output filenames as
physical configuration. It was corrected to normalize only those output paths.
The long-control readback also exposed a directory-prefix collision: a
`continuous-*` glob included `continuous-long`. Selection now uses the recorded
case identity with directory/process checks and a dedicated regression. The
original 36 executions were reread without rerunning Native. These failed logs
are preserved.

Removing only array-domain clocks has a structural limit. In a long steady
interval the extra array-only wakes are about `1/3.76 - 1/94` per ns, compared
with a total `1 + 1/3.76 - 1/94`; the limiting reduction is about **20.34%**.
External admission retains some of those wakes. This explains the measured
count reduction, not the wall-time ratio. Every 1 ns NoC/compute boundary still
invokes the system; this experiment does not measure which remaining Python
phase or IPC operation dominates its CPU cost.

P2.1's restricted joint service is validated; P2.2 has nonzero **conservative**
coordination reduction; P2.3 has only modest runtime benefit. A supply-eligibility-
only active system coordinator is still unimplemented. Keep the backend opt-in
and reject unsupported inventories. Do not extend this result to full FFN,
layout fidelity, a general DRAM service abstraction or a universal speedup.
Further work would need a safe contract for active NoC/system input and its
interaction with memory admission, rather than more porting of this singleton
frontend. No second island or general scheduler is implemented by this receipt.

Compact provenance is in `artifacts/provenance/memory_service_island`, with
[byte-verified publication](../../artifacts/provenance/memory_service_island/PUBLISHED_COPIES.json).
The new bridge SHA is
`78a0a94cebea61d3e639f41d95505d90fe2346d5dd6368ced87f231281ac387d`;
all 155 BookSim build inputs are unchanged, and Ramulator remains at
`72427a1bba3771564c4fb0e494ba02242fd1eaa7` with the recorded original library.
