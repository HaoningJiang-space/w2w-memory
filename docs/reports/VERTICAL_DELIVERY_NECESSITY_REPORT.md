# Vertical delivery: separate bypass from physical organization

This is a saved-evidence structural screen, not a new architecture performance
result. Source `3233bb3` reads hash-bound completed Up-local cold/two-layer
captures and the bounded Down-prefetch foil. No Native commands, old executable
timing, cache policy or physical machine were changed. Eight directed hn072
checks cover the new contracts and captured-routing interface.

## The strongest reference needs a delivery bypass

The proposed 128 Domain-aligned logic tiles combine two different changes:
removing shared collection and replacing SRAM-mediated first-use delivery with
a finite FIFO. A **16-Gateway-to-PE FIFO reference** can also implement the
second change. It must be compared at the same operand readiness, retention
policy and finite control/storage cost before SRAM-read savings are credited
to Domain alignment.

Cerebras already describes a weight stream that triggers computation without
storing weights temporarily. Direct streaming itself is therefore not a new
WoW capability. Its published physical unit is a small core; the current
simulator's sixteen clusters aggregate thousands of those cores. A matched
128-tile *resolution reference* must retain the old Gateway, collection,
storage ownership and shared grants. Merely exposing smaller tiles must not
create extra service resources. [Cerebras architecture description](https://www.cerebras.ai/blog/cerebras-architecture-deep-dive-first-look-inside-the-hw-sw-co-design-for-deep-learning).

Three organizations should consequently be distinguished:

| Organization | Delivery | Status |
|---|---|---|
| Current Up-local | Domain → collection → Gateway → SRAM → compute | Executed and independently audited |
| Gateway bypass reference | Same collection/Gateway; finite FIFO → compute, optional paid retention write | Non-executable contract |
| Domain-direct candidate | Per-domain HB/FIFO → local tile; paid activation/scale network | Non-executable specification |

Bypass requires X/H, original FP8 scales and a real PE grant. If a miss is
retained, its cache write must still be accepted; tee backpressure is real.
Otherwise fetch must be deferred or data spilled, with storage and subsequent
read charged. Hit data still needs SRAM reads. A bypass is neither a free cache
fill nor a guarantee that all arriving words can immediately be consumed.

## Existing readiness does not fit a 64-byte FIFO

Current operands become available after committed **4 KiB descriptors**. The
minimum holding space for even one opaque ready descriptor exceeds 64 B. A
4 KiB staging RAM can retain this interface, but compute then reads that RAM;
moving it does not remove the SRAM read. A 32 B readiness interface plus 64 B
FIFO is a distinct hardware protocol requiring finite reordering, validity,
credits and retention arbitration, not an equivalent replacement already
implemented by the current kernel.

Saved-event replay, preserving existing commit/consume times, gives these
lower bounds for unconsumed committed FP8 miss bytes:

| Cold policy | Maximum per cluster | Maximum per matrix |
|---|---:|---:|
| Current Up-local | 65,536 B | 49,152 B |
| Bounded Down prefetch | 528,384 B | 524,288 B |

These bounds omit partial precommit receive writes, scale/activation storage
and native reservations. They are not recommended FIFO sizes for a changed
32 B protocol. They show why a small FIFO cannot preserve the old schedule
without backpressure or earlier consumption. In particular, an early Down
matrix may have to wait for H while storing all its FP8 weights.

At 32 B readiness, two whole 512 KiB matrices need 4,112 B of prefix validity
state per neighborhood under the existing bitmap rule. Eight 64 KiB slices,
two frames each, need 4,224 B. Most of this metadata is the cost of finer
readiness and must also be charged to the Gateway bypass reference. The
existing native return reservation remains 64 × 16 B per domain, 131,072 B
across 128 domains; it is additional to receiver holding and prefix state.

## A directory reference can preserve capacity without eightfold tags

For the fixed 524,416 B matrix, the old 184 MiB cache can hold 367 complete
objects. Eight equal 23 MiB pools, with a common derived slot and a 65,664 B
maximum slice stride, also hold 367. Padding is 896 B per matrix. This uses
**collective whole-matrix replacement, pinning and slot ownership**; it does
not provide independent partial hits, partial eviction or capacity pooling.

Keep 512 original 128-bit tags and add paid eight-bit valid and filling masks:
tag storage becomes 9,216 B rather than 8,192 B. Including the retained 32
lookup associations and base state, the minimum directory metadata is 9,616 B
per neighborhood, versus 8,592 B. Associative ports, active frame associations,
banking, wiring, clocks and macro area remain unclosed. Equal independent tag
counts instead give only 64 slice entries per tile, about 4 MiB resident data;
512 independent tags on every tile would multiply the tag budget by eight.

This is a residency-capacity reference, not a cache-traffic prediction. New
execution order can change misses even with the same collective policy.

## Measure the removed path and charge the replacement

For each actual domain, audited returned atoms × 16 B × declared collection
distance reconstruct Memory-wafer collection activity. It is separate from
the previously reported global NoC activity.

The counterfactual local star routes every frozen logical demand: full X to
eight Gate and eight Up tiles, original shared scales from their single owner,
U collection/scatter, H collection/full-vector fanout and eight output slices.
It pays one 128-bit header per message, 16-bit sideband per word and payload
padding. No free X reuse, multicast, fused U exchange or output bypass is
assumed. Down scales are output-local; aligned physical padding remains paid.
The old macrocluster's unresolved internal movement is conservatively credited
zero. This favors the old organization; it is not a matched physical model of
both organizations.

| Quantity | Cold Up-local | Recorded 24-token/two-layer Up-local |
|---|---:|---:|
| Observed native weight bytes | 151,031,808 | 2,017,952,768 |
| Observed collection byte·µm | 1.11386×10¹² | 1.48824×10¹³ |
| Observed global NoC byte·µm | 9.71321×10¹⁰ | 4.02354×10¹² |
| Added local header/data/sideband bit·µm | 9.81186×10¹¹ | 4.70969×10¹³ |
| FP8 first-use reads potentially bypassed | 150,994,944 B | 2,017,460,224 B |
| All FP8 streaming reads | 150,994,944 B | 7,247,757,312 B |

In the repeated workload the first-use upper bound is **27.84%** of FP8 weight
read activity, not 100%. Cache-hit reads, original scales, retention writes,
activation accesses and staging reads are not automatically eliminated.
These repeated-workload values still describe the historical **layer-route
reuse proxy**, not the newly imported complete real-routing corpus.

The fixed star requires 241,664,000 data wire bit·µm and 30,208,000 sideband
wire bit·µm. These are additional local logic wiring, not area-calibrated
silicon. Removing collection is not a proof that total wire, clock or energy
cost decreases.

Let e_logic/e_memory have the same energy-per-bit-distance units. A conditional
transport screen is

    e_logic × added_local_cell_bit_um + incremental_residual_energy
        < e_memory × observed_collection_bit_um.

Setting *every other increment to zero*, the ratio thresholds are **9.082**
for cold and **2.528** for repeated execution. Those are break-even conditions,
not calibrated energy, EDP or candidate latency. The residual includes control
serialization, FIFO/directory/buffer work, extra padding reads, CDC/clocks and
static cost. The candidate also cannot be assigned the current cache misses
without an execution proof; this screen holds them fixed solely to isolate
delivery work.

## Decision

The 128-tile specification has an identifiable possible advantage: removing
measured Memory-wafer collection work. Its necessity is **not yet established**.
First establish finite word-level delivery for the Gateway bypass reference
and candidate at matched readiness, local tile resolution, directory capacity
and grants. Then test whether direct Domain delivery produces a physical
advantage after the paid local activation/scale network and residual costs.

Do not start a full 128-tile Native application matrix or report PPA from these
contracts. Keep the completed Down-prefetch regression and current Up-local
as the executed references. The complete real MoE trace restoration is tracked
separately in [CAPTURED_MOE_TRACE_REPORT](CAPTURED_MOE_TRACE_REPORT.md).
