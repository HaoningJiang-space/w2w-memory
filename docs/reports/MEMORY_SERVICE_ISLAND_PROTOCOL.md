# Native memory-service island: fixed small gate

Execution source will be committed before the first run. New builds, tests and
captures run only in a fresh hn072 `w2w-full-system-memory-island-*` directory.
P0/P1 evidence and accepted native binaries remain immutable.

The first island is explicitly restricted to one physical RWDL domain, one
owning Gateway and one bank-group view. Ramulator still performs every array
tick, command, arbitration and refresh. The new native frontend reproduces
descriptor ordering, atom acceptance, finite return reservations, range/ACK
control, collection/CDC and Gateway output. No array or NoC rate is fitted.

Three inputs exercise continuous return, two-atom return pressure with the
declared Gateway access delay, and an externally timed second request. The
pressure case tests reservation backpressure; it must not be mislabeled as
contention between multiple Gateway inputs. Each ordinary/island pair uses the
same declared capacities and workload. Full evidence is retained on both sides.

`advance_until(external_limit)` stops at the first externally relevant frontier
or the known input cap. First returned data is observable even before the first
flit threshold: the current kernel admits response NI storage on a nonzero
prefix. Subsequent supply eligibility uses `(prefix+header)//flit`, with the
final padded flit and descriptor completion handled explicitly. ACK capacity
release is also observable. No unknown future input may be bypassed.

The initial system integration retains every NoC/compute clock and every
descriptor-admission DRAM boundary. Only DRAM-only/internal-frontend wakeups
are delegated to the island. It does not claim demand-aware BookSim advancement
or a scheduler that wakes exclusively on flit supply. Native internal ticks and
frontend steps are reported separately from system iterations.

The first port-only attempt still called Native on every host wake and produced
no wall-time benefit despite fewer system iterations. Its gate is preserved.
The bounded revision uses a state-derived next internal boundary (array tick,
pending frontend event, or nonempty Gateway service) to avoid empty calls and
empty logic phases. An external submission invalidates that certificate. No
future callback time is assumed, and no DRAM/refresh tick is removed.

Component accuracy compares timestamped ready atoms, complete control evidence,
finite resource records and all Ramulator commands/stats to ordinary
`VerticalRWDL`. System accuracy also requires physical events/results, endpoint
progress/mutations, operand frontiers, task completion and final drain equal.
New-request insertion must be handled before the next internal issue decision;
wrong clocks, unsupported geometry and advancing past known input caps fail.

Use repeated unprofiled workers for all three cases. Compare full worker wall,
execution wall, process CPU (including synchronous native DRAM), BookSim child
CPU, RSS, host wakes and frontend steps. Counts are not converted to a promised
speedup. If event equality or performance fails, preserve and report the failure;
do not broaden to FFN or a second island.
