# Exact compute epochs in a small native system

The first system compute epoch is accepted for its restricted contract. Execution
source is `467548926cb7c9a32fcc22b20441a5f351a84b6e`; stronger independent readback
is `935cb4eb0d69f3b0cf4360165d23aa0c5201527f`. New execution, builds and tests ran
on hn072 in `/Projects/haoning/w2w-full-system-compute-epoch-20261010`.

This extends exact batching to the existing system kernel, with native DRAM,
HB/control and remote Compute Mesh transport. It does not substitute a network
backend or change physical capacity, bandwidth, clocks, arbitration or compute
readiness. The switch defaults off. It is not a complete FFN speedup receipt.

## What can be skipped

One running streaming context must have all weights/scales committed. Reads,
MC reservations, network packets/credits, memory frontend callbacks and other
contexts must be absent. The transition applies the existing arithmetic/read
rate, keeps the final short service outside the batch, and stops at release and
deadline barriers. Cache execution and an event observer disable it.

The NoC and compute clocks match in this first rule. DRAM retains its 3,760 ps
clock and phase; there is no assumed global 2 ns period. Ramulator's ordinary
advance executes every internal DRAM clock, including refresh, on resumption.
Only already drained BookSim uses its existing idle clock synchronization.
Active transport, return, VC, credit and command service are never skipped.

Full recording still produces each ordinary compute event. Compact records one
constant-service interval, expanded by an independent reader. The system,
vertical and control audits operate on the expanded full result. Counters-only
system output and an interactive transport/compute macro are not implemented.

## Accepted evidence

The full suite at the execution source passed **41 tests**, with native tools
enabled. A later targeted recheck passed **7 tests**; these suites overlap and
are not additive. They cover original-cycle equality, tail/deadline/release
boundaries, unknown backend rejection, multiple contexts, unavailable data,
pending credit, observer fallback and forged interval metadata.

Four fixed cases ran off/Full/Compact; the stable case has three shuffled
repetitions, giving **18 native system workers**. Every physical result field
matches after removing only kernel iteration/epoch bookkeeping and established
path/build provenance fields. Expanded compute events, task timing, consumption,
resource peaks/lifetimes, endpoint mutation/progress/completion fingerprints,
native command/address/timestamp fingerprints and final drain all match.

| Case | Off iterations | Epoch iterations | Batched compute cycles | Application / drain |
|---|---:|---:|---:|---:|
| Stable remote streaming GEMM | 22,215 | 4,316 | 14,258 | 17.696 / 17.696 µs |
| Non-divisible final service | 5,247 | 1,879 | 2,683 | 4.179 / 4.179 µs |
| Release between clock edges | 22,216 | 4,320 | 14,256 | 17.696 / 17.696 µs |
| Transport-dominated GEMM | 1,872 | 1,872 | 0 | 1.433 / 1.490 µs |

The supplemental audit independently reconstructs consumed work before/after
each interval and the union of omitted NoC/DRAM/compute clock boundaries. Its
count exactly matches the observed iteration reduction; it does not trust the
reported batch total. Raw process commands and original artifact hashes also
pass readback. The transport case is retained as a valid zero-coverage result.

Stable-case complete worker medians over three repetitions are **1.553 s off,
1.092 s Full (1.42×), and 1.002 s Compact (1.55×)**. Execution-only medians are
1.071 / 0.636 / 0.656 s. Compact is not faster on every timing measure. Full
retains all 17,453 event rows; Compact saves 3,196 rows. Arithmetic/state work
reduction and evidence reduction are separate benefits. Initialization, native
service and serialization still limit end-to-end speedup.

These synthetic GEMMs use the original machine's MAC/SRAM service budgets with
explicit reuse of 4,096 or 5,461 MACs/weight-byte; they are not full FFN inputs
or product calibration. Do not extend 1.55× to complete placement studies.

The first startup attempt used an incompatible old 16 MiB-only DRAM bridge and
is retained as `gate-001`, unaccepted. A new bridge was built from current source
against pinned Ramulator. The accepted bridge SHA is
`37eb00768993fb5cfd903c690e72a21cdc69e10f4acbc421762f54dc5a33ba54`.
BookSim SHA is `9d18611aa0cc74b6d8a475e302134c7888b1417648607abce3a6f8d04311e308`;
all 155 registered build-input files matched before reuse. Off/on use identical
binaries. A supplemental checker initially rejected the frozen-source symlink
spelling; that failed diagnostic is preserved and the corrected reader passes
without regenerating any native result.

[Verification](../../artifacts/provenance/compute_epoch/VERIFIED.json),
[supplemental checks](../../artifacts/provenance/compute_epoch/SUPPLEMENTAL.json),
[native/environment identities](../../artifacts/provenance/compute_epoch/ACCEPTED_ENVIRONMENT.json)
and [byte-verified published copies](../../artifacts/provenance/compute_epoch/PUBLISHED_COPIES.json)
point to the raw `gate-002`, tests and build files on the server. Large native
captures and result tables remain there.

## Compute Fabric abstraction remains a separate question

The read-only tensor fan-out audit uses explicit logical tensor/storage identity
from lowering. It does not merge unrelated equal-size transfers. The frozen
Reference/Balanced/Hybrid compute and fabric inputs have 680 materialized copies,
489 logical groups and **one fan-out group**. Fixed-route activation payload
accounting is 6,520,832 byte-hops with per-consumer copies; the union of those
paths accounts for 1,728,512 byte-hops. These quantities are identical across
the three memory layouts.

This is a sharing opportunity, not an executable multicast result or a prediction
of actual adaptive hop-flits. Branch capacity/control, buffers, retained source
data, receive copies and time-varying consumer eligibility still need an explicit
contract. Equal static opportunity does not imply equal timing or unchanged
ranking when competing weight streams differ. No multicast policy was silently
added to the existing kernel. [Raw accounting](../../artifacts/provenance/compute_epoch/FABRIC_FANOUT.json)
retains input/source hashes and per-tensor groups.

The newer controlled gate/up result also prevents an overly simple locality
explanation: keeping Hybrid's down placement/addresses fixed while striping
gate/up gives 544.288 µs versus 562.863 µs, despite the larger hop-flit count.
See the [existing stage report](PLACEMENT_STAGE_MECHANISM_REPORT.md). This is a
declared-policy/address intervention, not a pure propagation or multicast test.

## What this establishes

The proof is that a certified compute-only part of a native multi-clock system
can replace repeated host state updates without changing physical events. It
does not yet cover partial-input epochs with active returns, multiple interacting
contexts, cache behavior, multicast or general cross-component compression.
Next development should target one such boundary explicitly, keeping this exact
fallback and same-policy reference. Independent G2.2/G2.3 and a full placement
matrix are not prerequisites for this system work.
