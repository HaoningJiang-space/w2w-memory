# Whole-layer SRAM residency: completed strong reference

With all 128 experts of one FFN layer initially resident, **24 consecutive
archived decode tokens finish in 658.065 µs**, with **zero DRAM weight bytes**.
The frozen graph has 11,760 tasks. Independent raw native, tensor, cache,
compute-service and storage audits pass. This is a conditional warm interval,
not an end-to-end startup measurement or full LLM inference result.

| Metric | Measured value |
|---|---:|
| Sequence completion | 658.065 µs |
| Mean completion interval / token | 27.419375 µs |
| Initial weight residency | 2,416,508,928 B |
| Logical GEMM weight reads served by SRAM | 3,624,763,392 B |
| Matrix cache hits | 6,912 |
| DRAM read descriptors / weight bytes | 0 / 0 |
| Gateway weight bytes | 0 |
| Compute Fabric hop-flits | 1,050,852 |
| Activation/result transfer payload | 117,768,192 B |

The 24 decode steps and all-expert static catalog match the registered
[memory-hierarchy protocol](MEMORY_HIERARCHY_PROTOCOL.md). Each cluster has
192 MiB physical SRAM, a paid 184 MiB weight partition and 8,592 B lookup/tag
state. All weights occupy 144.035 MiB per cluster. No compute, receive-write,
fabric-facing SRAM read or arithmetic service was added. Two waiting contexts
share one arithmetic/read grant per cycle. Input/result copies remain explicit.

The initial layer load is outside the warm interval, not free. Its full bytes
are recorded; the 512 GB/s total gateway interface gives a **4,719.744 µs
necessary initial-load bound**, before array, command, CDC and transport losses.
It is not a measured startup time. No cold-vs-warm speedup is reported because
the previous cold one-token routing and this sequence are different inputs and
have different amortization scopes.

The result confirms that the entire modeled layer can reside in distributed
SRAM and can avoid all repeated vertical weight reads. It weakens a motivation
based only on repeating one cold layer. The registered two-independent-layer
cases are still running; they must establish actual compulsory/capacity reloads
and compare Central+ with Distributed before a persistent DRAM or multi-layer
performance claim is made. A cumulative accessed set exceeding SRAM alone does
not prove a particular eviction/reload count or its critical-path contribution.

Execution source: `3fb523ecf878e715044a35324d44b8ab0f20e1e3`.
BookSim SHA-256: `1ed98923175373524b293487d20aa4918596edfc92d28c6c87756e4996530e88`.
Selected completion, independent audit and raw-file hashes:
[`artifacts/provenance/memory_hierarchy`](../../artifacts/provenance/memory_hierarchy/).
Raw result:
`hn072:/Projects/haoning/w2w-full-system-gateway-cache-20261009/hierarchy-study-r1/cases/single-layer-warm/result.json.gz`.

Fixed four-way partitioning, conservative tensor copies, ideal receive booking,
aggregate SRAM/compute service assumptions and uncalibrated area/power remain
limits. This does not model attention, normalization, residuals, KV-cache or
numerical outputs.
