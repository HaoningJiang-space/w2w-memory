# Committed operand readiness

A small complete native FFN gives the same integer-ps completion time with
aggregate byte-count readiness and with a committed contiguous matrix prefix.
Central completes in **108.102 µs** and Distributed in **107.576 µs** under both
policies. This is a limited sensitivity result, not proof that the full-size
or two-layer cache studies are insensitive to operand order.

| Organization | Byte count (µs) | Contiguous prefix (µs) | Difference (ps) |
|---|---:|---:|---:|
| Central | 108.102 | 108.102 | 0 |
| Distributed | 107.576 | 107.576 | 0 |

The probe uses one token selecting experts 0 and 1, four statically laid-out
experts, hidden dimension 4096, intermediate dimension 512, and four partitions.
Both organizations use the same graph and placement, two finite contexts,
finite ready-aware injection on all 16 routers, physical request/ACK control,
the existing native RWDL arrays and BookSim. Refresh is disabled and no weight
cache is enabled. Each case reads **12,585,984 B** from the same native services.
Compute, receive write, native command and fabric resources are unchanged.

Central has nine committed deliveries with a prefix hole, across three tasks;
at most 8192 already committed bytes lie beyond a missing prefix. The prefix
policy records 394 blocked task/clock observations for each of three gate
GEMMs. These observations are not additive critical-path stalls, and they do
not move the final completion in this probe. Central arithmetic service sums
to 3.119 µs under byte count and 3.113 µs under prefix: the same MAC work can
pack into a different number of partially occupied service cycles. Distributed
has no observed holes and sums to 3.115 µs under both policies.

## What the policies mean

The default byte-count policy assumes that any committed matrix bytes can be
consumed out of order by the aggregate compute resource. It does not implement
the activation selection, indexed accumulation or bank arbitration needed for
a specific out-of-order datapath. This assumption remains explicit.

The alternative consumes data in increasing matrix byte-offset order. Its
frontier advances only when canonical 4096 B descriptors have committed;
the final descriptor may be shorter. It does not introduce native-atom-level
compute or bypass the current receive/commit boundary. Validity bitmap plus
64-bit frontier/association state is charged within task SRAM. The observed
peak is 48 B on each active cluster; all frontier state drains. Both policies
retain the same full matrix storage reservations and shared arithmetic/read
grant. A cache hit, when used, becomes fully ready after the finite tag lookup.

An intentionally delayed-descriptor causal fixture delivers a later chunk
before the first chunk. Byte-count execution can advance before that first
chunk; prefix execution cannot. The independent auditor rejects interpreting
that byte-count execution as prefix. This fixture uses native BookSim but is
not a DRAM performance experiment. The four-case probe above uses native RWDL.

## Physical guards and migration

The supported collection timing profile requires at least
`max(1, ceil(length_um / 1000))` stages at the declared clock. Unknown timing
profiles and shorter pipelines are rejected. Additional paid stages are legal.
Duplicate domain/gateway collection pairs are rejected before runtime dictionary
construction. The frozen recipes keep their existing generated delays.

The relevant remote suite passed 24 checks at `24b52c6`; the final preset
derivation passed four physical-contract checks and the causal readiness check
at `f999bd2`. The default small FFN completes in 54.489 / 54.143 / 54.748 µs
for Central / Distributed / the corrected perimeter External reference.
Historical full-size results are retained under their original identities.
The migration also matches the recorded task times, SRAM peaks, arithmetic and
context service, MC pool peaks, native counters/timing and network counters
exactly. A separate offline pass re-audits all four raw probe results.

Execution source: `f999bd2855d2673fb6ccaaaf81b9a03cd2b946ca`.
BookSim SHA-256:
`1ed98923175373524b293487d20aa4918596edfc92d28c6c87756e4996530e88`.
Ramulator bridge SHA-256:
`37eb00768993fb5cfd903c690e72a21cdc69e10f4acbc421762f54dc5a33ba54`.
Large inputs and raw results are retained at
`hn072:/Projects/haoning/w2w-full-system-gateway-cache-20261009/operand-readiness-r1`.
Selected analysis, remote check logs and raw SHA-256 inventory are in
[`artifacts/provenance/operand_readiness`](../../artifacts/provenance/operand_readiness/).

```sh
python -m w2w.experiments.probe_operand_readiness \
  --output NEW_DIRECTORY --booksim-binary BINARY
python -m w2w.analysis.operand_readiness \
  --source COMPLETED_DIRECTORY --output AUDIT_JSON
```

The registered two-layer experiments keep source `3fb523e` and byte-count
readiness. This small probe does not change their running execution or promote
their unfinished results to a performance claim.
