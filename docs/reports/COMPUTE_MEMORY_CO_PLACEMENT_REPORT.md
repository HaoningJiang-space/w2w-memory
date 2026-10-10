# Up-local computation: cold transport result and finite-cache continuation

The controlled cold gate succeeds at the **delivery-cost objective**, with only
a small extra latency gain. On fixed Phase-Split weights and existing hardware,
moving Up arithmetic to its Gateway-local compute cluster reduces NoC data-lane
activity **87.78%**, while completion improves **1.08%**. The 24-token two-layer
pair is registered and running; no completed Up-local multi-layer claim is made.
Fetch-controller optimization and fragment execution remain closed/deferred.

## What changes, and what does not

Execution is frozen at `02dab2a`, introduced by the mapping changes at `d31f03c`.
The final independent cold readback is `3b7851a`. No kernel, native simulator,
physical topology, Gateway, HB lane, MAC, SRAM, read port, descriptor/outstanding
budget or matrix format is changed. Two coupled fetch slots/136 B and two
shared-service compute contexts remain active at every cluster.

All three cells use the same full 128-expert Phase-Split catalog, addresses,
scales and S1 mathematical graph. Only Up task tiles change. Gate, Activation,
Down, ordered sums, reductions and token input/combine stay at the reference
compute locations. Real X/U DataEdges use existing finite read/write, packet,
router/credit and SRAM services. No free input broadcast, cache transfer or
new tensor alias is added. Arithmetic stays entirely on the compute wafer.

The nonlocal diagnostic matches the Up-local **per-cluster** task, MAC, weight
read and scratch work. Up executes at another same-reticle cluster, away from
both its original compute node and its actual weight Gateway. Independent
readback confirms actual per-cluster MACs and stream weight bytes also match.
This call-specific, known-work matching is a mechanism control, not a proposed
static catalog policy. It does not fix dynamic arbitration, dependency times
or path distances. Thus its timing difference is not an exclusive NoC stall.

## Completed cold comparison

| Fixed Phase-Split weights | Original Up compute | Up-local compute | Matched nonlocal Up |
|---|---:|---:|---:|
| Complete time (µs) | 456.627 | **451.676** | 517.708 |
| Native/Gateway bytes | 151,031,808 | 151,031,808 | 151,031,808 |
| Read descriptors | 37,152 | 37,152 | 37,152 |
| Mathematical tasks | 490 | 490 | 490 |
| Fabric hop-flits | 470,616 | **51,432** | 678,792 |
| Intra-reticle hop-flits | 453,060 | **33,876** | 661,236 |
| Cross-reticle hop-flits | 17,556 | 17,556 | 17,556 |
| Data-lane byte·µm | 794,654,284,800 | **97,132,108,800** | 1,328,574,028,800 |
| Remote Up-weight payload (B) | 50,343,936 | **0** | 50,343,936 |
| Remote X→Up payload (B) | 737,280 | 737,280 | 737,280 |
| Remote U→Activation payload (B) | 0 | **49,152** | 49,152 |
| Maximum Gateway payload-work bound (µs) | 344.148 | 344.148 | 344.148 |

Up-local removes all horizontal Up-weight payload; the small Up result is
instead transferred to the unchanged Activation consumer. X is not free:
786,432 B is delivered to Up in every case, including 737,280 B with different
source/destination routers. The equality of remote X bytes is an observed
feature of this call's endpoints, not a universal result or a claim that paths
are identical. Per-Gateway bytes and per-physical-domain atom work are also
identical across the cold cells.

Relative to original Up compute, latency falls 4.951 µs, hop-flits fall 89.07%
and executed data-lane activity falls 87.78%. Relative to matched nonlocal,
Up-local is 12.75% faster with the same planned and executed per-cluster MAC/read
work. Merely distributing Up work therefore does not guarantee this result.
The control also changes physical delivery and resource-feedback timing.

For context only, the already frozen `869f0ac` S1 Reference-weight result is
580.576 µs with 98,969,164,800 data-lane byte·µm. Up-local retains the independent
Phase-Split weight services while returning lateral activity to about that
historical level (1.86% lower), and is 22.20% faster than that historical
Reference. This is not a new execution of Reference weights or a causal
Up-placement-only comparison; the three cells above are the controlled gate.

## Why the latency improvement is small

NoC activity and latency are different objectives. The fixed Gateway assignment
still needs 344.148 µs of payload work on its busiest Gateway in every cell.
Its whole-interval effective payload fraction changes only from 75.37% to
76.19% with Up-local. The old data transfer can pipeline behind the slower
vertical supply; removing most of its activity need not remove comparable time.
Neither this utilization nor the work bound proves an exclusive bottleneck.

The matched final expert-62/block-8 timeline directly shows another interaction:

| Observed milestone (µs) | Original Up compute | Up-local compute |
|---|---:|---:|
| Previous block sum finishes | 410.271 | **380.889** |
| Gate admitted | 410.271 | 384.428 |
| Gate final descriptor issued | 429.222 | 423.206 |
| Gate finishes | 432.095 | 427.180 |
| Up admitted | 410.271 | 380.889 |
| Up final descriptor issued | 429.343 | 398.710 |
| Up finishes | 432.198 | **402.685** |
| Gate/Up join | 432.198 | 427.180 |
| Down finishes | 454.034 | 449.083 |
| Layer finishes | 456.627 | 451.676 |

The block releases 29.382 µs earlier, and Up finishes substantially earlier.
But Gate becomes the latest projection: release-to-join grows from 21.927 to
46.291 µs. That 24.364-µs increase consumes most of the earlier release benefit.
The final gain is only 4.951 µs. Thus moving computation changes the timing and
competition of remaining requests, not just the distance of one transfer.
The matched nonlocal cell finishes through a different expert-10 chain; it is
not compared as if its final tasks were this expert-62 block.

These are exact matched dependency milestones. They are not an additive stall
decomposition or proof that one queue alone caused the change. Two finite
contexts, coupled fetch state, real arrivals and the same previous-block barriers
remain. No new controller experiment is justified or run from these observations.

## Correctness and source identity

Sixteen relevant remote tests pass at `d31f03c`, including the old mapping and
sequence contracts, small native Up-local cold execution and a finite-cache
case with real hits, evictions and reload. Three overlapping mapping/readback
tests pass at `3b7851a`, including unknown policy and stale remote-preload
rejection. Counts are not added as distinct test coverage.

The complete original-Up cold physical record matches the old `869f0ac`
Phase-Split record after documented source/build-path canonicalization. Cold
and multi-layer default input fingerprints are unchanged from their accepted
archives. All cold cells use the same pinned native tools. Independent audits
check source/input/graph identity, fixed weight addresses and data/control edges,
actual MACs, physical domains and byte work, finite compute/fetch/outstanding,
command/ACK control, receiver/SRAM capacity and complete drain. Maximum cold
SRAM peaks remain below 2.9 MB versus 192 MiB physical capacity per cluster.
No native transactions, mathematical work or participating competition were
removed to obtain lower activity.

The model remains a timing/data-movement proxy: no numerical inference,
silicon-calibrated SRAM banking or PPA is newly validated. The existing ideal
global receive booking and aggregate compute assumptions remain. Native callback
and BookSim progress semantics are unchanged. Data-lane byte·µm includes actual
executed flit/padding/header activity; remote endpoint counts are logical
committed payload. Neither is a joule measurement.

## Registered finite-cache pair: running

Both 24-token/two-layer cells were frozen before cold performance was inspected.
They start only after the independent cold correctness gate passes; latency is
not an acceptance filter. Worker source is still `02dab2a` and the original two
coupled slots remain. The input-routing and Phase-Split addresses, mathematical
work and all physical budgets are fixed.

Up-local's L0 Up cache objects move to their actual compute consumers **before**
measurement. Both cases preload the same full L0 object catalog/global order and
**2,416,508,928 B**. Exactly 1,536 Up objects change cluster; Gate/Down initial
objects retain their original cluster. Each cluster initially contains
151,031,808 B / 288 entries, within 184 MiB / 512 cache limits. This is an
explicit separately initialized warm condition, not free remote cache hits or
a timed migration. Actual later hit, miss, reload, per-cluster working set and
native service are allowed to differ and will be reported.

Native workers are PIDs 589801 / 589802; the campaign controller is 589606.
A separate analysis-only finisher at `04f2e70` is PID 591118. After both
completions it independently audits the saved pair against the old `9160207`
Phase-Split reference and writes `multilayer/independent-readback.json`,
`completed-summary.json` and `COMPLETED_RESULTS.md` in the execution archive.
It preserves zero reload and negative performance and never retries simulation.
No completed multi-layer Co-Placement result is asserted here.

## Research verdict and evidence

This first gate supports **preserving independent vertical service while avoiding
large horizontal weight transfers on existing hardware**. It does not support
a large further latency gain, a novel hardware claim, calibrated energy/EDP,
optimal placement or broad Decode/Prefill generality. The transport reduction is
the material result. Multi-layer cache behavior is the next required check before
changing any physical hardware organization.

The registration contract is in
[the protocol](COMPUTE_MEMORY_CO_PLACEMENT_PROTOCOL.md). Derived proofs, source/
input/native/raw SHA identities, launch records, preload budgets and test logs
are in `artifacts/provenance/co_placement`. Raw captures stay on hn072 under
`/Projects/haoning/w2w-full-system-co-placement-20261010`; the running source
worktree is immutable. No RTL, sibling simulator or other developer's workspace
is modified.
