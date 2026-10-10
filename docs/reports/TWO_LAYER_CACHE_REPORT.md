# Two-layer finite weight-cache result

The 24-token two-layer FFN proxy completes in **15.030022 ms** with Central+
and **13.281470 ms** with Distributed, a **11.6337% completion reduction**.
Both runs complete all 48 layer invocations and pass independent raw hierarchy/
cache/control audits. Each invocation has identical hit/miss/reload/native-byte
counts between the two organizations. The difference is not fewer weight reads.

Frozen execution source:
`3fb523ecf878e715044a35324d44b8ab0f20e1e3`, unchanged throughout the runs.
Both use R3 BookSim
`1ed98923175373524b293487d20aa4918596edfc92d28c6c87756e4996530e88`.
The implementation/file identities and raw hashes remain separate from the
newer operand-aware study. Selected evidence is in
`artifacts/provenance/memory_hierarchy/{two-layer-analysis.json,
two-layer-evidence-sha256.json,invocation-traffic.json}`. Raw files stay under
`/Projects/haoning/w2w-full-system-gateway-cache-20261009/hierarchy-study-r1`.

## Capacity and execution contract

The [registered protocol](MEMORY_HIERARCHY_PROTOCOL.md) uses two distinct full
weight catalogs, finite 184 MiB weight cache within each 192 MiB cluster SRAM,
LRU without future information, pinning of filling/in-use matrices and finite
tag lookup. Startup preloads the complete first layer (2,416,508,928 B), excluded
from the measured interval. The second layer is cold. Initialization is not
free; the existing preload lower bound is 4.719744 ms at total gateway output,
before array/transport losses.

Total catalogs occupy 4.501 GiB. The accessed set is about 3.024 GiB, above
3 GiB physical SRAM; the busiest cluster exceeds its physical capacity. The
cache is inside that SRAM budget, not added to it. Matrices are immutable,
whole-object cache entries; misses use the existing finite native/HB/gateway/
SRAM path and hits retain the same arithmetic/read grants.

Both have two shared-service contexts, the same finite ready selectors and
physical command/ACK protocol with refresh. **This registered execution uses
byte-count operand availability**, not the newer contiguous-prefix policy.
The second layer reuses the first layer's archived routing as a proxy. Attention,
KV, normalization, residuals and numerical tensors are not modeled. These are
two distinct FFN weight banks, not a complete Transformer or a stationary trace.

## Completed ledger

| Observation | Central+ | Distributed |
|---|---:|---:|
| Complete interval | 15.030022 ms | 13.281470 ms |
| Native/gateway weight bytes | 2,265,477,120 | 2,265,477,120 |
| Hit bytes | 4,984,049,664 | 4,984,049,664 |
| Compulsory miss bytes | 1,623,591,936 | 1,623,591,936 |
| Reload bytes | 641,885,184 | 641,885,184 |
| Hits / misses | 9,504 / 4,320 | 9,504 / 4,320 |
| Evictions / evicted bytes | 3,056 / 1,602,615,296 | 3,056 / 1,602,615,296 |
| Hop-flits | 23,423,784 | 2,101,704 |
| Busiest RX write service | 1.747576 ms | 1.698814 ms |
| Busiest arithmetic service | 72.866 µs | 72.378 µs |
| Ready-behind-unsupplied with credit, source×cycles | 0 | 0 |

The total logical weight consumption is 7,249,526,784 B; hit plus miss bytes
equal it exactly. Control range counts are equal (4,440,960), with 71,055,360 B
commands and 35,527,680 B ACKs each. Reservations and temporary SRAM drain;
cached residency is separately retained under its finite capacity contract.
Distributed still pays extra control resources; the comparison is not equal PPA.

## Late-window traffic, not just cold startup

Separate offline analysis at `1a92654` assigns actual lookup and committed read
events to each registered invocation, verifies the global cache counters and
checks native bytes equal misses. It does not regenerate an LRU schedule or
infer traffic from capacity alone.

For **token 12–23**, the last 24 layer invocations:

| Observation | Central+ | Distributed |
|---|---:|---:|
| Window elapsed | 7.302808 ms | 6.373886 ms |
| Native bytes | 1,019,464,704 | 1,019,464,704 |
| Compulsory bytes | 434,216,448 | 434,216,448 |
| Reload bytes | 585,248,256 | 585,248,256 |
| Hit / miss calls | 4,968 / 1,944 | 4,968 / 1,944 |

Distributed reduces this finite-window elapsed time by **12.7201%**. Reload
accounts for 57.4% of late native bytes: continued DRAM service is not explained
only by the second layer's initial compulsory fills. This establishes ongoing
capacity-driven rereads for this trace; it does not establish a universal
steady-state rate or the best possible cache policy.

The [warm-layer reference](WARM_LAYER_REFERENCE.md) remains strong: 24 tokens,
658.065 µs, 6,912 hits and zero DRAM weight reads when the complete layer is
resident. It must not be replaced by forced rereads. Zero reload also remains a
valid result for other traces, although these two runs do observe reload.

The cold prefix-aware pair's 25.66% and this study's 11.63% are different
workloads/contracts and cannot be subtracted to attribute a cache contribution.
The evidence supports vertical service usefulness under this finite working
set and a conditional spatial-access advantage. It does not prove whole-LLM
performance, SRAM macro feasibility, optimal central fanout or wafer-scale PPA.
