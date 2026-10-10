# Causal boundary census: opportunity observed, active coordination not achieved

P0 is complete. The minimal P1 passes its first-callback primitive and fallback
checks, but has **zero certified active intervals** in all three native system
inputs. Kernel iterations did not decrease and no acceleration is claimed.
This closes the first-callback-only, quiet-frontend candidate; it does not prove
that more general feedback-aware coordination is impossible.

Execution source is `4daf6e4`, independent evidence readback `d987cf0`. New
builds/tests/runs are archived on hn072 under
`/Projects/haoning/w2w-full-system-causal-boundary-20261010`. Keep the accepted
interactive/quiescent records and sibling network receipts unchanged.
[Protocol](CAUSAL_BOUNDARY_PROTOCOL.md) fixes the small inputs and constraints.
The [independent verdict](../../artifacts/provenance/causal_boundary/VERDICT.json)
separates evidence correctness from the failed acceleration goal. The
[paired worker receipt](../../artifacts/provenance/causal_boundary/VERIFIED.json),
[environment](../../artifacts/provenance/causal_boundary/ACCEPTED_ENVIRONMENT.json)
and [test log](../../artifacts/provenance/causal_boundary/TESTS.log) preserve the
checked identities and results.

## What the census actually observes

Diagnostics preserve the original time driver and phases. Per host wakeup they
count interface progress, successful/failed admission, native array callbacks,
Gateway-ready atoms and a declared projection of resource-related state.
The projection contains owners, ready tasks, outstanding/MC pools, NI/RX
occupancy, native reservations/pools, Gateway queue lengths and operand heads.
It is deliberately **not** a complete causal state. No observed change is not
a guarantee of safe lookahead; recorded event production is not proof of
necessary synchronization. Category counts overlap and must not be added.

Stable and transport are the prior fixed inputs. The concurrent case has two
tasks on c2/c3 reading one shared 8 KiB object from m0_0, reuse 256 MAC/byte,
ordinary one-context-per-cluster service. Clocks, capacities and service rules
are unchanged. Instrumented runtime is not used as a performance measurement.

| Case | Host wakes / clock union | With observed interface progress | Without interface or projected resource change | Of those, compute service | Conservative active-array gaps |
|---|---:|---:|---:|---:|---:|
| Stable | 22,215 / 22,215 | 3,192 | 18,665 | 14,570 | 0 |
| Transport | 1,872 / 1,872 | 639 | 1,185 | 0 | 0 |
| Concurrent | 2,185 / 2,185 | 1,094 | 965 | 170 | 0 |

All wakeups in these inputs lie in the exact NoC/DRAM/compute clock union.
For stable, inclusion-exclusion gives
`1 + floor(17696000/1000) + floor(17696000/3760) - floor(17696000/94000)`
`= 22,215`. The descriptive clock/observed-interface ratios are **6.96, 2.93,
2.00**; none is an achievable speedup bound or a count of necessary events.

The stable case has 18,562 post-wakeup states with no pending array read.
Only 3,653 have pending array reads. Much of the quiet execution is the already
studied compute tail; a strictly active-array optimization cannot relabel that
tail as new coverage. The P0 gap test is only a necessary-condition projection
for the conservative P1, not a general maximum-compression calculation.

## Where synchronization remains

| Measured count | Stable | Transport | Concurrent |
|---|---:|---:|---:|
| Python DRAM advance calls | 22,215 | 1,872 | 2,185 |
| Actual bridge advances / internal DRAM ticks | 4,706 | 396 | 462 |
| Native callback atoms | 4,098 | 514 | 1,028 |
| Wakes with native callbacks | 764 | 182 | 297 |
| Wakes with Gateway-ready atoms | 2,219 | 309 | 611 |
| Native atom issue attempts / successes | 5,844 / 4,098 | 1,027 / 514 | 1,567 / 1,028 |
| NI admission attempts / successes | 226 / 34 | 6 / 6 | 12 / 12 |
| BookSim wire replies during the host loop | 3,436 | 1,457 | 1,669 |
| Advance replies without progress/completion | 2,523 | 1,328 | 1,431 |

One callback wake can return many atoms. API mutation calls are coalesced; they
are not individual wire round trips. The census counts actual `_receive()` wire
replies separately. Empty replies still advance native router/credit and source
pressure state; absence of returned progress does not certify absence of useful
internal service. C++ execution is not removed by reducing Python calls.

In stable, the domain issue queue is nonempty at **3,620** sampled wakes, NoC is
not Idle at **4,313**, Gateway queues are nonempty at **2,145**, and receiver
waiters exist at **2,315**. These overlap substantially. Backend read-buffer
acceptance and Gateway service cannot be postponed to a data callback without
preserving their own eligibility and timing. BookSim Idle is also stronger than
an empty reply: unsupplied queued messages and credit/drain work remain relevant.

## The minimal P1 and its result

The new bridge can run ordinary Ramulator clocks until its **first callback**
or a certified cap. It reports the stop cycle and retains callbacks until the
system resumes there. New DRAM input is rejected during that reservation,
including when the cap is reached without a callback. Internal command/row and
refresh behavior remain upstream.

The coordinator only attempts this with one funded prefix context, native NoC
Idle, no local/receive events, no pending request issue, empty domain/Gateway
queues and an active array request. Frontend events, release, prefix exhaustion
and deadline cap the interval. Queue service is not silently skipped. Compute
events inside a valid interval retain their original service times and order;
tail/completion and callback processing use the original phases.

**60 tests pass**, including native first-callback versus tick-reference command
traces/stats through 20 µs with refresh, hidden callback delivery, locked input,
known-event/deadline barriers, bulk compute state equality and forged-resume
rejection. This is a tested primitive/guard, not a native system compression
receipt. The first full test attempt exposed an audit gap: changing resume could
leave the same compute count. The final audit additionally binds Native stop
cycle and callback count. That failed log remains archived.

Fifteen workers compare ordinary/interactive Full/coordinated Full: three stable
repetitions and one each of the other cases, shuffled with fixed CPU affinity
18/19. Every physical event/result, endpoint fingerprint, command/time/address
fingerprint and final drain is equal. The new bridge's ordinary path also
matches the old accepted stable/transport records and fingerprints, allowing
only the changed bridge identity. Diagnostic runs match their uninstrumented
ordinary results. Atom admission ticket zero is counted correctly; the first
census's incorrect success counter is preserved and excluded.

| Case | Ordinary / interactive / coordinated iterations | Certified P1 intervals | Completion / drain |
|---|---:|---:|---:|
| Stable | 22,215 / 22,215 / 22,215 | 0 | 17.696 / 17.696 µs |
| Transport | 1,872 / 1,872 / 1,872 | 0 | 1.433 / 1.490 µs |
| Concurrent | 2,185 / 2,185 / 2,185 | 0 | 1.740 / 1.740 µs |

The registered **40% wakeup-reduction target is not achieved**. This is not a
success hidden behind an `audit passed` field: the supplemental verdict explicitly
sets `active_coordination_demonstrated=false` and
`wakeup_target_40_percent_achieved=false`.

Same-batch stable medians (three repetitions):

| Mode | Complete worker | Execution | Python CPU | Stored events |
|---|---:|---:|---:|---:|
| Ordinary | 1.583 s | 1.094 s | 1.008 s | 17,453 |
| Interactive Full | 2.175 s | 1.573 s | 1.374 s | 17,453 |
| Coordinated Full | 2.206 s | 1.677 s | 1.472 s | 17,453 |

There is no measured gain. These costs are not compared to an older batch's
1.312-second worker as a speedup ratio; the same-input baselines here share the
same new bridge, evidence mode and process controls. The candidate is default
off. Do not extend a zero-coverage small gate to full FFN performance or layout
ranking. No application matrix or hardware policy was changed for this study.

## What to do with this negative result

Do not simply replace all ticks with a guessed next callback. The current
module boundary still puts admission retries, finite Gateway output and supply
coordination in Python. The next useful investigation is one of:

* a native certificate for the next **eligibility** change, including request
  capacity rather than just completed data;
* joint domain-frontend/Gateway service preserving finite reservations and its
  first external supply boundary;
* demand-aware NoC progress with a proven no-new-input horizon, retaining
  internal steps/counters and immediate receive/credit effects.

Select one using the measured call/feedback structure. The census does not
measure the CPU share of each candidate and cannot promise 2× or 40%. Expanding
the quiet-frontend P1, changing timing, or counting quiescent compute skips again
would not solve the observed active coordination problem.

Raw captures, build products and wakeup tables stay on hn072. Compact checked
receipts are in `artifacts/provenance/causal_boundary`; their
[publication manifest](../../artifacts/provenance/causal_boundary/PUBLISHED_COPIES.json)
binds remote paths and copied byte hashes. The build reuses all **155 unchanged
BookSim inputs**, pinned Ramulator library `72427a1…`, and a new reviewed bridge.
Its SHA is `2f0ce7820967b76977ebaca5f10b66bdb809c34f76e1afdcf4aec21a709ebb1a`.
