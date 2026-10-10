# Full-size operand-aware vertical access

Distributed completes the matched cold FFN in **581.384 µs**, versus
**782.060 µs** for Central+, a **25.6599% completion reduction**. Both raw
results pass separate offline byte, operand, context and command/ACK audits.
The advantage persists with committed contiguous operands and finite admission-
priority scheduling; it is not evidence that every optimized Central design
would lose by this amount.

Execution and offline audit source:
`8a8e34bd9ca451b2e3ecb1c7fcf0a0eca53a692f`. The R4 BookSim binary and preserved
DRAM bridge are the same in both cases. Registration, analysis and exact input/
raw/completion hashes are in `artifacts/provenance/operand_access`; raw captures
remain on hn072 under `operand-access-r1`.

## Matched contract

One archived decode token selects eight experts from the frozen 128-expert
catalog: hidden 4096, intermediate 1536, four partitions. The complete logical
FFN, 490-task graph, weights/addresses and compute placement are identical.
This is timing/data movement, not numerical Qwen model validation.

Both use the same 16 compute clusters, 3 GiB SRAM, 128 physical native domains,
8 GiB DRAM, 16,384 HB data lanes and 512 B/ns total gateway output. The array
timing/read queues, refresh and compute fabric are unchanged. Two contexts share
one existing arithmetic/read grant. All 16 routers have the same paid 16-entry
ready selector (3 KiB total metadata), prioritized by oldest admission among
ready messages. Central+ still has one physical injection per region; no ports
or throughput are added by selection. No weight cache is enabled.

Contiguous-prefix validity/frontier state is charged in task SRAM. It commits
canonical 4 KiB matrix descriptors and does not consume a later range through a
missing earlier operand. Peak per-cluster state is at most 72 B in either run;
the final metadata live count is zero. This is a strict timing contract, not
address-aware out-of-order hardware.

Central and Distributed match data/service budgets, not all physical costs.
Distributed has **1,536 additional declared control bits** across HB/gateways.
Its collection data-wire proxy is 120,832,000 bit·µm smaller. Fixed fabric,
staging and descriptor budgets are retained; these proxies are not equal PPA.

## Observations and limits of attribution

| Observation | Central+ | Distributed |
|---|---:|---:|
| Complete FFN | 782.060 µs | 581.384 µs |
| Native payload | 151,031,808 B | 151,031,808 B |
| Last native beat tail | 779.436720 µs | 578.750480 µs |
| Compute-fabric hop-flits | 1,463,556 | 52,536 |
| Busiest executed channel service | 138.410 µs | 6.564 µs |
| Busiest SRAM write service | 117.828 µs | 114.345 µs |
| Busiest arithmetic service | 3.503 µs | 3.400 µs |
| Ready-behind-unsupplied with credit, source×cycles | 0 | 0 |

Physical per-domain read counts are identical. The last-native time difference
is 200.686240 µs, while completion differs by 200.676 µs: a 10.240 ns difference
between those deltas. Access organization changes the finite request/return/
consumption feedback, not just final propagation distance. This observation is
not a decomposition of critical-path stalls or proof that one internal queue
causes the whole gain. Partial arithmetic grants can change busy-cycle packing
without changing MAC work.

The configured middle x and y cuts each carry **8,778 macro cells in both
cases**, with eight independent directed channels: 1,123,584 data-lane bytes and
a 1.097250 µs executed-volume bound per cut. This includes cell headers/packing,
with sideband resources counted separately. The reduced weight traffic is
predominantly within each memory/compute region. This experiment does **not**
demonstrate a wafer bisection bottleneck or remove one.

| Necessary work bound | Central+ | Distributed |
|---|---:|---:|
| Busiest native domain/dedicated HB service | 415.931200 µs | 415.931200 µs |
| Busiest gateway payload / allocated output | 294.984 µs | 442.476 µs |
| Busiest executed channel | 138.410 µs | 6.564 µs |

Do not sum these overlapping bounds. Distributed actually has a higher gateway
work bound: per region its four outputs receive 9,439,488 / 9,439,488 /
4,719,744 / 14,159,232 B at the same 32 B/ns allocation. The hottest gateway
uses 464,701 output cycles, about 79.9% of the full interval. Avoiding central
collection has not eliminated spatial load imbalance. This motivates studying
static placement versus locality with the existing resources before adding
more gateways; it is not a forecast of gains from such a placement.

Ideal instantaneous remote RX booking, aggregate SRAM banking, assumed array
timing and the macro representation of a fine fabric remain limits. External
uses a separately costed, lower-output-budget proxy and has not been made a
resource-matched product baseline. There is no central fanout/PPA optimum claim,
prefill measurement, numerical inference or PIM.
