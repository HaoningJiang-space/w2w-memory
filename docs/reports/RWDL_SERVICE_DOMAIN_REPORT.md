# Independent RWDL service and operand-aware access gates

The equal-byte service probe is complete. Eight independent domains finish the
same 256 KiB read in 11.087 µs, compared with 84.779 µs when all addresses use
one domain. This establishes useful channel parallelism in the current native
candidate. It is not an application speedup or measured hardware validation.

Execution source: `f30829960fb654dfd256aeec1c17216894bbda4b`. Separate offline
audit source: `8a8e34b`. Both use the R4 BookSim binary
`ccb3c9f852d42b6b8a554cc789c232d1b749a0c7ef8f28a4526be976c61c9f58`
(built at `9a787a7`) and the retained native DRAM bridge
`37eb00768993fb5cfd903c690e72a21cdc69e10f4acbc421762f54dc5a33ba54`.
Every R4 build-input SHA matches these execution checkouts; native code was not
changed for this experiment. Raw records remain under
`/Projects/haoning/w2w-full-system-gateway-cache-20261009/rwdl-domain-r1` on hn072.

## Gate A: equal data, different physical address distribution

Both runs compile the same Central V3 stack, including both address-space views.
The uniform view stripes native 32 B words across eight existing domains. The
hot view references only the first of those domains. It does not create an array,
controller, HB port, MC descriptor pool or additional capacity. Exactly one
256 KiB object is read in each run; overlapping views are not independent copies.

| Observation | Eight uniform domains | One hot domain |
|---|---:|---:|
| Required / native / gateway / SRAM payload | 262,144 B | 262,144 B |
| Actual 16 B RD commands | 16,384 | 16,384 |
| RD commands per active domain | 2,048 | 16,384 |
| Complete read task | 11.087 µs | 84.779 µs |
| Last native data-beat tail | 10.937840 µs | 84.618800 µs |
| Payload / complete interval | 23.644 GB/s | 3.092 GB/s |
| Peak shared MC descriptors | 32 | 32 |
| Peak native atom reservation | 50 | 50 |
| Peak gateway collection queue | 128 B | 16 B |
| SRAM write service | 2,048 cycles | 2,048 cycles |
| SRAM write-job wait sum | 0 | 0 |
| Compute-fabric hop-flits / arithmetic work | 0 / 0 | 0 / 0 |

The hot/uniform completion ratio is 7.6467, not an assumed factor of eight. Row
changes, refresh, finite admission, command/ACK serialization and physical
collection remain active. A local requester avoids adding remote compute-fabric
competition to this service probe. Its request and response still pay gateway
access, native service, coordinate-derived collection/HB, CDC, finite staging,
payload DMA and the same receive write port.

| Necessary interface/work bound | Eight uniform | One hot |
|---|---:|---:|
| Busiest native domain / dedicated HB lane | 7.700480 µs | 61.603840 µs |
| Shared gateway output at 128 B/ns | 2.048 µs | 2.048 µs |
| Receiver payload at 128 B/ns | 2.048 µs | 2.048 µs |

These bounds overlap and are not summed. HB and native data-beat work describe
the same dedicated RWDL service, not two serial charges. The gateway is not
saturated in this fixture. Command counts and rejected admission attempts are
observations, not independent critical-path stalls.

### Independent checks

The native command recorder preserves all 128 controller traces, including idle
read domains' refresh. Offline verification reconstructs the exact physical RD
address multiset from the graph and immutable memory views. It checks one issued
command/domain/cycle, matching open rows, row/column bounds, declared ACT/PRE/RD/
REF timing gaps, and first/last callback timestamps against issued RD plus
`nCL+nBL`. The separate vertical and control audits verify byte conservation,
command/ACK credit ownership, finite reservations and complete drain.

The selected records and hashes are in
[`artifacts/provenance/rwdl_domains`](../../artifacts/provenance/rwdl_domains).
Idle read-domain command totals are summarized; hashes retain every full trace.
Malformed early reads, wrong operands, overlapping command cycles and early
post-refresh ACTs are rejected by the directed audit fixtures.

This is read-only evidence. The standard declares WR constraints, but neither
this probe nor its audit establishes write-path correctness. The 128-bit RWDL
and 3.76 ns anchors come from [SeDRAM](https://doi.org/10.3390/electronics12051077);
the V3 512-Mbit/domain capacity, array/refresh timings, aggregation and control
implementation are declared research assumptions, not a reproduction of its
128-Mbit channel implementation. This is not complete physical or silicon closure.

## Gate B: registered full-size operand-aware comparison

The pair is frozen at `8a8e34b` and completed in
`execution-operand-access-r1`, with results under `operand-access-r1`. The
registration and launch identities are retained in
`artifacts/provenance/operand_access`. Independent raw audits pass: Central+
782.060 µs versus Distributed 581.384 µs, a 25.6599% reduction. See
[OPERAND_AWARE_ACCESS_REPORT](OPERAND_AWARE_ACCESS_REPORT.md) for bounds and scope.

Both Central+ and Distributed use the same archived `c0_b1` routing, 128-expert
static weight catalog, eight selected experts, addresses, compute placement and
complete 490-task FFN graph. They retain two contexts sharing the existing MAC/
read grant, request/ACK control, staggered refresh, the same physical 128 native
domains, total HB lanes, SRAM and gateway data budgets. A finite 16-entry selector
is enabled at every router in both cases (3 KiB metadata each machine); its
priority is oldest-admitted among ready. It does not add a physical injection
port or duplicate throughput. No weight cache is enabled in this cold-read pair.

The compute policy is **contiguous-prefix committed matrix descriptors**, with
its bitmap/frontier state paid in task SRAM. It cannot consume a later fragment
through an earlier missing operand. This follows the completed small policy
probe; it is distinct from the still-running hierarchy study's byte-count policy.

The 60-second monitor stops on failure and independently audits raw results
after both cases complete. Analysis records native/domain work, gateways, RX,
actual hop-flits, arithmetic/context service and executed x/y mesh-cut volume
bounds. It does not add overlapping wait counters into a total stall.

Central+ remains a single physical central injection per region. Distributed
changes collection and injection locations; it must pay additional control and
layout costs. This pair does not establish superiority over every central
fanout/controller design. External remains a separately costed reference, with
128 GB/s total output versus 512 GB/s vertical gateway output and a different
control contract; it is not inserted into an allegedly equal-budget comparison.

## Gate C and research limits

The completed 24-token two-layer cache experiments remain frozen at `3fb523e`,
with their original native binary and byte-count execution contract. They are
not rerun or re-labelled as operand-aware. Warm single-layer residency already
gives zero DRAM weight reads; zero reload is also a valid negative observation.
The current monitor accepts only a fully re-audited instance of the old runner's
specific zero-reload post-run rejection, and retains execution/analysis identities
separately. Both completed with actual reload and independent audits: 15.030022
versus 13.281470 ms (11.6337% reduction). The late half also has nonzero reload;
[TWO_LAYER_CACHE_REPORT](TWO_LAYER_CACHE_REPORT.md) records the finite window.

The two independent layer weight catalogs create real aggregate/per-cluster SRAM
pressure, but reuse archived routing at the second layer. They remain an FFN-only
proxy. Prefill and attention/KV/norm/residual Transformer execution have not been
measured. Ideal global RX reservation and aggregate SRAM banking remain explicit
limits. Resource proxies are not PPA.

[Cerebras Weight Streaming](https://www.cerebras.ai/blog/announcing-the-cerebras-architecture-for-extreme-scale-ai)
already streams externally stored weights by layer, so streaming itself is not
the proposed contribution. The [DAC 2025 centralized/dual-I/O study](https://doi.org/10.1109/DAC63849.2025.11132870)
motivates a strong Central baseline rather than a presumed Distributed winner.
[ATLAS](https://arxiv.org/abs/2604.08044) reports silicon-based simulation error
within 8.57%; that is the authors' validation claim and does not calibrate this
simulator. The present research question is how physical native service,
vertical exposure and static placement deliver usable service to compute under
finite resources. Computation remains on the logic wafer; this is not PIM.
