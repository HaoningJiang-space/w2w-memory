# Domain-aligned logic organization: specification and counterexample gate

The candidate changes where vertical data is delivered, which logic resources
own it, and which storage operations are necessary. It is not a new NoC/MAC
parameter sweep. The first implementation is a **non-executable architecture
specification**, full-catalog output-row layout and finite numerical oracle,
plus a bounded whole-matrix Down-prefetch counterexample on the existing
machine. No latency, energy or area result is attributed to a 128-tile machine.

## What the current model actually represents

The sixteen 4,096-PE clusters aggregate a distributed compute fabric; they are
not a claim that Cerebras implements sixteen processors with monolithic
192 MiB caches. Public Cerebras material describes local 48 KiB SRAM, fine
dataflow execution and native broadcast/multicast. An eight-way subdivision of
each simulator cluster can expose concurrency the aggregate model suppressed.
That alone is a model-resolution change, not evidence for new hardware.
[Cerebras architecture deep dive](https://www.cerebras.ai/blog/cerebras-architecture-deep-dive-first-look-inside-the-hw-sw-co-design-for-deep-learning).

The existing best Up-local mapping already consumes **Gate, Up and Down
weights at their owning Gateway-local cluster**. Its local X/U/H tensor
movement is explicitly charged. Thus moving all three full matrices to local
compute is not an additional intervention. The missing controlled capability
is Down **fetch** before H, while Down **compute** still waits for H.

## Mathematical partition and exact scale ownership

For a 128-element intermediate block and hidden width 4,096:

| Projection | Each of eight domains owns | FP8 data/domain | Reduction required before its output |
|---|---|---:|---|
| Gate | 16 complete output rows × 4,096 columns | 65,536 B | Full 4,096-column dot product |
| Up | 16 complete output rows × 4,096 columns | 65,536 B | Full 4,096-column dot product |
| Down | 512 complete output rows × 128 columns | 65,536 B | All 128 gated elements |

Gate/Up row partition preserves the hidden reduction. SiLU is applied only to
a complete Gate result; Up is multiplied afterwards, H is converted to BF16,
and each Down output retains the original ordered FP32 dot product. Down rows
concatenate within a block. Accumulation between intermediate blocks and tensor
partitions still needs the original ordering and resources. No hidden-dimension
partial is treated as a legal SiLU input.

The original FP8 quantization group stays 128×128. All eight Gate/Up slices
reference the **same 32 original FP32 scales**: one owner stores 128 B and the
others require real scale delivery. They do not gain eight new scale groups.
Each Down slice owns four scales, 16 valid bytes. The declared 32-byte storage
and read alignment pads this to 32 B/domain, so a Down matrix occupies 128 B
more than its original representation. Full 128-expert packing includes all
4,608 matrices, fits each physical domain, and adds **196,608 B** of padding.
The cold active set adds **12,288 B**, reading 151,044,096 B rather than
151,031,808 B. Offline packing defines an initial memory image; measured runtime
transpose/gather or migration is not silently omitted.

The finite E4M3FN/BF16 oracle verifies exact output-row equivalence with shared
scale identities and preserved reduction order on synthetic matrices. This is
an executable mathematical contract, not numerical inference by the native
timing simulator or a calibration against a real model's quantization format.

## Why row partition does not automatically make a pipeline

At 16 B per 3.76 ns, each domain needs **15.40096 µs** for 64 KiB of data.
The scale owner needs at least 15.43104 µs for Gate/Up; a padded Down slice needs
15.40848 µs. These are payload work bounds, excluding ACT/PRE/refresh, admission,
control, CDC and all transport/compute feedback.

Uniform domains processing sixteen full rows finish their complete H slices
at approximately the same time. Down output-row partition still needs the
**entire H vector**. This is different from splitting Down by intermediate
columns and accumulating partial vectors. Smaller ownership slices therefore
do not, by themselves, shorten the G/U → H → Down dependency barrier.

Earlier per-row outputs would arrive in sets such as `{16i + t : i=0..7}`.
Consuming these immediately changes the Down access pattern and may change
FP32 accumulation order. That needs a separate layout/readiness contract; it
is not implied by this output-row specification.

If Down weights are fully prefetched while waiting for complete H, each tile
needs **64 KiB of storage**, or 512 KiB per eight-domain neighborhood. A 64 B
direct FIFO cannot hide a full Down fetch. Either SRAM must hold those weights,
or a different legal partial-accumulation mechanism must be implemented.

## Conserved resources and new costs

| Resource | Current distributed machine | Domain-aligned specification |
|---|---:|---:|
| Logic aggregation units | 16 clusters | 128 domain tiles in 16 neighborhoods |
| PEs / MAC per 1 ns | 65,536 / 262,144 | Same |
| Physical SRAM / weight budget | 3 GiB / 2.875 GiB | Same; 24 MiB / 23 MiB per tile |
| Native domains / capacity | 128 / 8 GiB | Same identities |
| HB data / control signals | 16,384 / 1,024 | Same; 128 / 8 per landing |
| Return staging / MC descriptor entries | 524,288 B / 128 | Same totals; 4 KiB / one per tile |
| Requester outstanding descriptors | 512 | Same total; four per tile |
| Matrix issue contexts | Two per cluster | Two shared per neighborhood |

The candidate's 64 B direct FIFO and 32 B association storage per tile are
inside the existing non-cache SRAM, not additional free SRAM. Two shared issue
contexts are retained; merely creating 128 Python objects must not create
256 independent matrix controllers or eight times as many arithmetic grants.
Finite staging entries are repartitioned, so their borrowing and lifetime
semantics change even though the total count is unchanged. Local SRAM banking,
PE utilization, association tags/ports and flow control remain to be closed.

Naively giving every new landing the old 64 control signals would add 7,168
signals. The equal-budget specification instead has four forward and four ACK
signals per landing, at the declared 1 ns control clock. A 128-bit command
then serializes in **32 ns**, a 64-bit ACK in **16 ns**, before propagation,
CDC and queueing. The existing native frontend accepts only the original
32+32-bit Gateway protocol; it deliberately cannot execute this proposal.

At the existing candidate 4 µm landing grid, equal signal counts occupy
278,784 → **294,912 µm²** after rectangular packing, a **5.79% increase**.
Actual footprints lie within aligned regions and do not overlap. This checks
landing geometry, not process feasibility, clock/power routing or the area of
compute/SRAM macros.

Removing the old memory collection branches removes 120,832,000 bit·µm of
declared data wire. A 128-bit logic-side star from the same neighborhood root
to the eight domain positions has **the same one-way wire proxy**; a dedicated
bidirectional version has at least twice that amount. A real implementation
could use narrower, shared or tree links, with explicit bandwidth and buffers.
Moving wires between wafers is not proof of lower total wire area or energy.

The combined native interfaces supply at most 544.681 B/ns versus the current
512 B/ns Gateway outputs. Removing that output cap can increase peak service
by only **6.38%** (about 6% lower ideal payload time). The candidate's cold total
work bound is 277.30752 µs; its most loaded domain bound is 323.8488 µs. Neither
is a simulated completion time or an achievable performance target.

Activation delivery also changes. Without reuse or multicast-edge accounting,
eight copies of X and H increase local sink bytes eightfold. A true multicast
tree may reduce edge traffic, but it must pay fanout, buffers and latency.
Down output slices need 2 KiB FP32 accumulator state per tile, 16 KiB total
per block, with finite read-modify-write service.

## Cache and direct-consumption mechanism

If eight slices are referenced in lockstep and both capacity and matrix size
are divided by eight, `C_i=C/8` and `W_i=W/8` preserve the collective number of
resident matrices. More local caches do not pool capacity. Unequal scales,
padding, asynchronous access and local replacement can make fragmentation
worse. The previous Up-local reload reduction consequently does not predict
a reload reduction for this candidate.

A direct path can avoid the **first-use SRAM weight read** for a cache miss,
provided a finite FIFO feeds the PE and can backpressure DRAM safely. Weights
retained for later tokens still require SRAM writes and later cache-hit reads.
Scale service, activation reads and accumulator writes remain. For the frozen
Up-local two-layer run, 2.017460224 GB of FP8 miss data is a potential first-use
read saving, not measured energy saved. Prefetched Down that waits for H may
still need SRAM, reducing the bypass benefit.

Streaming bandwidth hierarchies and spatial data reuse are established ideas;
they are not claimed as new here.
[Imagine author dissertation](https://www-vlsi.stanford.edu/people/alum/pdf/0306_Brucek_Imagine.pdf),
[Eyeriss author presentation](https://eems.mit.edu/wp-content/uploads/2016/06/eyeriss_isca_2016_slides.pdf).
The specific hypothesis is whether independent vertical delivery removes
enough collection/SRAM work to offset distributed control and activation service.

## Existing-machine counterexample

The frozen source `8d531a9` registers two cold cases: Up-local unchanged, and
Up-local with one bounded waiting Down per cluster. Gate/Up demand is admitted
first; Down may use an existing spare coupled Fetch Slot after its real input
and previous-block fetch prerequisites, without waiting for H. It still pays
full weight/H SRAM storage, real Native/RWDL/BookSim/receive writes, the original
two compute contexts and shared ports. Eight additional association bytes per
cluster are explicitly reserved and drained. All original mathematical start
dependencies remain in the graph. Cache execution is rejected for this foil.

The six directed tests on hn072 pass, including real native prefetch before H,
unchanged logical work and bounded outstanding/fetch resources. Complete cold
results are pending readback and independent analysis. A rerun of the default
case must equal every frozen Up-local physical record/event, not merely its
451.676 µs makespan. Negative prefetch performance is valid evidence and will
not trigger a retry or acceptance failure.

This spare-slot policy is a controlled, finite whole-matrix counterexample,
not a proof of the best possible whole-matrix scheduler. The twelve prior
fetch-state and completed multi-layer records stay frozen.

## Decision before a new physical runtime

The domain proposal refuses compilation. A future comparison needs three
matched models: the existing aggregate baseline; a 128-tile **resolution
baseline retaining collection/Gateway service and SRAM writes**; and domain
direct delivery with the same local compute, contexts and activation network.
Only the latter pair isolates the actual new data path from aggregation effects.

Proceed only after finite local multicast/reduction timing, serialized command
and ACK, scale ownership, cache/FIFO backpressure, SRAM banking and ordered
accumulation are executable and audited. First compare identical cold work and
matched cache residency; then allow the cache policy's real traffic changes.
Measure latency, separate memory/logic wire and activity, and conditional energy
with documented coefficients. No equal-PPA or calibrated energy claim follows
from the present specification.

The research gate is thus **a physically charged direct-delivery advantage over
the strongest supported whole-matrix implementation**, not the existence of
more tiles or a faster number from a finer-resolution model.
