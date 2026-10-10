# Active-prefix compute intervals: exact behavior, limited cost benefit

The first interactive-prefix experiment passes exact native comparison, but
does **not** establish an execution speedup. Computation can consume an already
committed prefix while DRAM and NoC remain active. Deferring repeated arithmetic
state updates preserves this behavior; continuing to visit the same host clock
boundaries limits the gain. The candidate remains optional and defaults off.

Execution source is `3c641f0` on hn072, under
`/Projects/haoning/w2w-full-system-interactive-epoch-20261010`. Stronger readback
sources are `c4b3e0e` and `44f95e1`. Source/build/raw records stay in their frozen
directories. The earlier accepted quiescent epoch and sibling network results
are unchanged. [Registration](INTERACTIVE_COMPUTE_PROTOCOL.md) fixes inputs,
guards, comparison and cost requirements before execution.

## Same behavior with active supply

The original Compute Mesh, remote memory home, finite gateway/NI/RX service,
BookSim and Ramulator (including refresh) execute normally. The system still
visits its original NoC/DRAM clock boundaries. This candidate never guesses the
next native arrival and never jumps the whole system past an active event.

A committed contiguous prefix funds a fixed number of service cycles for one
streaming context. During the interval the remaining source/kernel/native
phases run normally. Operand queries account for consumption already serviced;
no future consumption is exposed. Deferred fields are materialized before
fallback. The task tail, completion, SRAM release and downstream work use the
ordinary transition. Multiple contexts, cache and event observers fall back.

For the stable 64 KiB remote GEMM, the independently audited intervals are:

| Start | Original committed prefix | Consumed before → after | Cycles | Supply state at entry |
|---|---:|---:|---:|---|
| 1.312 µs | 4,096 B | 0 → 4,096 B | 1,024 | DRAM, transport and requests live |
| 2.336 µs | 32,768 B | 4,096 → 32,768 B | 7,168 | DRAM, transport and requests live |
| 9.504 µs | 65,536 B | 32,768 → 65,532 B | 8,191 | supply drained |

In the first two intervals, later descriptors commit **during** compute service.
The audit reconstructs the original prefix from the independent operand event
ledger; new arrivals do not retroactively enlarge an interval. The final four
bytes and task finish stay ordinary. Application and drain remain **17.696 µs**.

This is exact under the existing aggregate compute contract: one arithmetic/read
grant per cluster clock; committed descriptors; activation inputs fully delivered
before task start; full working sets reserved. RX credit is returned after SRAM
commit, rather than after individual MAC consumption. Compute emits downstream
work at task completion. No partial-output dataflow or consumption-driven RX
release protocol was added. Those policies would require new relevance guards.

## Accuracy and independent readback

Four fixed small inputs compare ordinary, quiescent epoch, interactive Full and
interactive Compact; stable has three shuffled repetitions, giving **24 native
workers**. All expanded physical records match, including compute events and
equal-time insertion order, task clocks, resource peaks/lifetimes, native
command/address/time fingerprints, endpoint mutation/progress/completion
fingerprints and final drain.

| Case | Ordinary host iterations | Quiescent | Interactive | Interactive weight services → arithmetic updates |
|---|---:|---:|---:|---:|
| Stable remote GEMM | 22,215 | 4,316 | 22,215 | 16,384 → 4 |
| Other-cluster release | 22,216 | 4,320 | 22,216 | 16,384 → 5 |
| Non-divisible tail | 5,247 | 1,879 | 5,247 | 2,742 → 2 |
| Transport dominated | 1,872 | 1,872 | 1,872 | 2 → 2 |

The update count includes ordinary weight updates and materialized service
intervals. It **does not count all execution work**: the stable interactive
controller still visits 16,383 batched service boundaries; every host/native
boundary remains. Full also creates every ordinary compute event. These are
distinct costs, not interchangeable skipped-cycle statistics.

The execution source passed **50 tests**. Supplemental targeted suites of 8 and
9 tests overlap that suite and add depletion/wait/recovery, zero-coverage fallback
and stricter evidence rejection; their counts must not be summed. **11 negative
checks on actual saved native evidence** reject corrupted frontiers, work counts,
duplicates, missing/unknown records and invalid equal-time anchors. The final
late-frontier negative expands first, so it challenges availability directly
rather than merely invalidating the compact anchors. The independent decoder
imports no execution code.
Compact preserves equal-time service positions with run-length encoded anchors,
not a timestamp-only merge. Saved-result checks verify interval/frontier/work
counts and each native worker against the original baseline. No application
matrix was repeated.

## Same-batch cost

Stable-case medians over three repetitions, fixed CPU affinity 18/19:

| Mode | Complete worker | Execution | Python CPU during execution | Python peak RSS | Stored events |
|---|---:|---:|---:|---:|---:|
| Ordinary | 1.312 s | 0.909 s | 0.841 s | 51,384 KiB | 17,453 |
| Quiescent Full | 0.967 s | 0.566 s | 0.501 s | 51,388 KiB | 17,453 |
| Interactive Full | 1.326 s | 0.926 s | 0.861 s | 51,544 KiB | 17,453 |
| Interactive Compact | 1.185 s | 0.917 s | 0.851 s | 44,824 KiB | 1,073 |

Interactive Full is slightly slower; Compact's complete worker is about
**1.11× faster**, while its execution median is slightly slower. Compact result
gzip size is about 38.5 KB versus 91.7 KB ordinary. Its observed gain is mainly
in evidence serialization/output, not faster native/system execution. Three
repetitions do not establish a statistically general speedup.

The matched quiescent epoch is about **1.36×** faster for complete worker in this
batch. Keep this separate from its previous 1.42×/1.55× measurements, which used
a different batch and quiescent evidence modes. Synthetic reuse is 4,096 or
5,461 MAC/weight-byte within unchanged service budgets; no full FFN, physical
calibration, architecture ranking or cross-component speedup is inferred.

The reused BookSim/DRAM binaries and **155 / 8 build-input files** match their
original manifests. Binary SHAs are respectively
`9d18611aa0cc74b6d8a475e302134c7888b1417648607abce3a6f8d04311e308` and
`37eb00768993fb5cfd903c690e72a21cdc69e10f4acbc421762f54dc5a33ba54`.
Pinned Ramulator library identity also matches. [Verification](../../artifacts/provenance/interactive_compute/VERIFIED.json),
[environment](../../artifacts/provenance/interactive_compute/ACCEPTED_ENVIRONMENT.json),
[native reuse](../../artifacts/provenance/interactive_compute/NATIVE_REUSE.json)
and [published byte checks](../../artifacts/provenance/interactive_compute/PUBLISHED_COPIES.json)
retain compact receipts; raw captures remain in `gate-001` on hn072.
The [final supplemental negative receipt](../../artifacts/provenance/interactive_compute/supplemental-r2/NEGATIVE.json)
and its [byte checks](../../artifacts/provenance/interactive_compute/supplemental-r2/PUBLISHED_COPIES.json)
bind the last reader/fallback regressions without regenerating any native result.

## Necessary information and the next boundary

A distinguishing-continuation regression holds committed fragment count and
contiguous head equal in two histories, but places the later fragment at a
different offset. Receiving the same next fragment yields different ready
prefixes (12 KiB versus 8 KiB). Both head and count alone are insufficient to
update future readiness; the validity holes or an equivalent representation
must remain. This is a necessary-information counterexample, not a theorem
that the retained state is minimal or sufficient for every future workload.

Predictive causal states and input-output processes provide a theoretical guide
([Shalizi–Crutchfield](https://csc.ucdavis.edu/~cmg/compmech/pubs/cmppss.htm),
[Barnett–Crutchfield](https://csc.ucdavis.edu/~cmg/compmech/pubs/et1.htm)). These
results do not make finite native equality a universal equivalence proof. The
interface observables, admissible continuations, resource policy and clock/order
contract must be stated. Distributional sufficiency and equality under every
legal continuation are different requirements.

This experiment closes the local deferred-update hypothesis: active supply does
not require re-solving the arithmetic service rate each clock, but removing that
work alone gives little execution benefit. Do not chase fairness parameters or
expand these cases. The next substantial optimization would need a component
contract for the **first externally observable event or certified lookahead**,
plus interruptible service intervals. Native feedback must still be handled at
its actual boundary. Until that exists, keep the exact fallback and accepted
quiescent rule rather than invent a global safe horizon.
