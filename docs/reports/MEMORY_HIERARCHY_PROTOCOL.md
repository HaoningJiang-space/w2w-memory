# Finite-SRAM multi-layer comparison: registered protocol

Status: the [single-layer warm reference](WARM_LAYER_REFERENCE.md) and both
two-layer cases are complete and independently audited. The protocol below
retains its registered workload and byte-count execution contract.
[TWO_LAYER_CACHE_REPORT](TWO_LAYER_CACHE_REPORT.md) records results and limits.
A completion is valid only after native/cache/control audits and the independent
analyzer pass. The completed context/selector intervention is in
[GATEWAY_CONTEXT_REPORT.md](GATEWAY_CONTEXT_REPORT.md).

## Workload and warm reference

Use the first 24 consecutive decode steps of the archived request
`Qwen/Qwen3-235B-A22B-FP8/mmlu/abstract_algebra/98.json`, without selecting tokens
based on performance. Source trace SHA-256:
`0a9933a9207fd02d20dd2a66b67537dd2c48e7320d54a298b78fb6078b729dae`.
The selection and archive hash are frozen in
[`two-layer-decode24.json`](../../configs/workloads/two-layer-decode24.json).

The FFN has hidden size 4096, intermediate size 1536, 128 experts and top-8
routing; it retains four intermediate partitions. Each layer has a complete,
static all-expert address catalog. Layer 1 uses independent storage and addresses
at the next free range of each physical domain group. Total catalog capacity
fits the same 8 GiB DRAM. No weight replication or DRAM service duplication is
introduced by gateway count.

Only layer-0 routing was archived. Both modeled layers therefore use the same
routing per token. This is a two-layer FFN timing/storage proxy, not a full
Transformer trace or numerical inference. Attention, norm, residual and KV-cache
are outside the workload. BF16 output of the first FFN is explicitly transferred
to the next; the next token starts after the previous token's final combine.

The 24 tokens visit 86 unique experts. Across two independent layers the accessed
weight set is **3.02418 GiB**, above the entire **3 GiB physical SRAM**, and the
busiest cluster needs **216.053 MiB**, above its **192 MiB** physical capacity.
This establishes actual accessed-set pressure, not just oversized inactive
catalogs or a deliberately tiny cache.
Accessed-set pressure does not prove a later revisit to an evicted object.
Zero reload is a valid outcome: completion depends on byte/resource/control
conservation, not on demonstrating the expected cache mechanism. Reload counters
include misses for initially preloaded objects as well as previously filled ones.

For the strong single-layer reference, ALL 128 layer-0 experts are initially
resident: **2,416,508,928 B**, **144.035 MiB per cluster**. This fits the declared
cache partition. The measured interval excludes this initial load; its bytes
and a **4,719.744 µs gateway-interface-only lower bound** are reported separately.
That is a necessary bound, not a simulated startup time or sustainable bandwidth.
The two-layer cases start with the same complete warm layer 0 and cold layer 1.

## Conserved resources and paid state

Each cluster retains 192 MiB SRAM, the existing MAC/read service and two finite
waiting contexts. One context at a time consumes the shared arithmetic/read
grant. The additional context pays 64 B scheduler state and all ordinary operand,
output and scratch storage remains reserved.

A **184 MiB data partition** is reserved inside each existing SRAM. The finite
matrix LRU uses 512 entries, 128 bits/entry, 32 pending lookup slots, one lookup
per cycle and 8,592 B metadata per cluster. This leaves approximately 8 MiB for
non-weight state. There is no lookahead. Fill/in-use entries are pinned; only
valid unpinned entries can be evicted. LRU recency follows admitted lookups rather
than variable fill-arrival order. A miss writes directly into the reserved
cache through the existing receive write port; a hit competes for the same
compute SRAM/MAC service. No second full matrix copy is silently reserved.

Central+ and Distributed use ready-aware selection at the SAME 16 physical
sources, 16 messages/source, 96 bits/message (**3 KiB** total metadata). They
retain their original physical injection locations and one cell/source/cycle.
HB data lanes, native domains/controllers, compute, SRAM, output bandwidth,
staging and MC descriptor budgets match. Port/control and physical wiring costs
remain different and are explicitly reported.

## Finite physical control contract

A gateway receives the ordinary fabric read packet, then pays a serialized 16 B
router-to-gateway control access and its declared physical propagation. A local
range frontend at each participating domain receives a **16 B command**, using
shared **32 forward/32 reverse HB control bits at 1 GHz**, one HB registration
cycle, coordinate-derived domain propagation and two native-clock CDC cycles.
The local frontend expands atoms; Ramulator retains ACT/PRE/RD/refresh ownership.

Credits remain reserved until the last atomic request of that range is accepted
and an **8 B ACK** traverses the reverse physical path, the shared reverse
serializer and two logic-clock CDC cycles. Neither native admission nor
array-local range completion frees remote credits instantly.

TX and ACK capacity follow the same regional descriptor/domain budget:
Central has 256 entries/gateway ×4; Distributed 64×16. Both pay **16 KiB TX** and
**16 KiB ACK** state. Each of 128 physical domains pays 32×16 B local range state,
**64 KiB** total. Extra control wires/pipeline bits and gateway access are recorded.
The first implementation requires one owning physical gateway/domain and has no
external-I/O protocol. It does not replace the remaining ideal global receive
booking abstraction. Controller/selector area, power and detailed SRAM conflicts
are still uncalibrated.

## Execution identity and completion

Frozen execution source: `3fb523ecf878e715044a35324d44b8ab0f20e1e3`.
BookSim SHA-256:
`1ed98923175373524b293487d20aa4918596edfc92d28c6c87756e4996530e88`.
Bridge remains
`37eb00768993fb5cfd903c690e72a21cdc69e10f4acbc421762f54dc5a33ba54`.

The source/model/native checks pass on hn072. The software-only BookSim completed
flit-history cleanup preserves exact small-FFN integer-ps timings and resource
counts against the previous binary. Default central/distributed execution also
matches the V3 migration fixture: 54.489 / 54.143 µs. New external locations are
intentionally different and are not included in that historical equality claim.

Registration/build identities are in
[`artifacts/provenance/memory_hierarchy`](../../artifacts/provenance/memory_hierarchy/).
Large inputs/captures are at
`hn072:/Projects/haoning/w2w-full-system-gateway-cache-20261009/hierarchy-study-r1`.
A 60-second monitor records invocation progress, stops on failures, and runs the
independent analyzer plus SHA-256 inventory after all three cases complete.
It does not silently retry or change frozen inputs.
If the frozen runner rejects only zero reload after saving a fully conserved raw
result, the current `--finalize-zero-reload CASE` mode can record a completion
without rerunning. It checks the registered input, execution source, exact retired
failure and independent audits, keeps the original execution identity, and records
the newer finalization source separately. Missing wall time is left unknown.

Required outputs: warm native bytes, hit/miss and compulsory/reload bytes,
evictions and pinned lifetimes, per-cluster residency/peak, native and gateway
byte conservation, command/ACK timing/serialization/drain, invocation completion
and conserved hardware budgets. Cache misses may differ through legal execution
feedback; they must be explained, not forced equal.
