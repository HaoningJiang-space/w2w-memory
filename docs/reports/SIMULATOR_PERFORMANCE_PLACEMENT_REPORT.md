# Simulator performance and memory-only static placement

P0–P3 are complete. P4 is running on hn072 and has no completed result in this
revision. Architecture V3 is unchanged; this stage optimizes simulator execution
and compares static memory layouts within the existing Distributed machine.

## P0: measured simulator costs

The full cold Central+ profile has 981,788 kernel iterations, 739.774 s execution
wall time, 679.810 s Python CPU and 66.104 s BookSim child CPU. Inclusive phase
times include 279.068 s in read issue, 150.317 s in native progress and 90.123 s in
memory progress. BookSim advance IPC takes 91.409 s. These timers overlap and
must not be added as a stall decomposition.

The full Distributed cProfile run records approximately 1.724 billion calls.
It exposes repeated endpoint/route resolution, blocked receive retries, native
atom-address construction, no-op prefix supply and JSON/pipe synchronization.
Its 734.543 s wall time includes cProfile overhead and is not the matched speed
baseline. The original kernel already deletes completed requests; there is no
evidence for a scan over all historical requests.

Child-launched py-spy native sampling succeeded on a small Central+ case
(921 samples, zero errors). A separately built gprof BookSim diagnostic exposes
JSON/protocol work, but its short sampled CPU duration cannot establish full-run
percentages. Host permissions deny perf and attached py-spy; no permissions were
changed. Native Ramulator advance/send calls have separate wall-time counters.
Raw profiles, sampled stacks and diagnostic binaries remain in the remote archive.

Evidence: [profiling.json](../../artifacts/provenance/simulator_performance/profiling.json).

## P1: faster execution with identical physical records

Both sides use the same full cold graph, command recorder and endpoint hashing.
Total wall time includes command audit and JSON/gzip saving.

| Case | Baseline total wall | Optimized total wall | Speedup | Unchanged makespan |
|---|---:|---:|---:|---:|
| Central+ | 1,052.950 s | 487.330 s | 2.161× | 782,060,000 ps |
| Distributed | 611.048 s | 294.213 s | 2.077× | 581,384,000 ps |

Execution-only times are 981.468 → 425.511 s and 544.529 → 224.016 s respectively.
This achieves the ≥2× engineering target in this matched measurement. It is one
same-host measurement with concurrent runs, not a statistical guarantee or a
comparison against uninstrumented historical wall times.

The improvements are ordered boundary IPC batches, deferred synchronization only
while native BookSim is proven idle, constant-time endpoint occupancy, cached
immutable endpoint/routes and native atom addresses, receive retries woken by MC
slot release, and processing only changed native return prefixes/admission retries.
Native Router/VC/credit processing, Ramulator ticks/refresh, physical clocks,
operands and all hardware budgets remain unchanged. The kernel iteration counts
are unchanged; no active interval is skipped speculatively.

The gate compares every Python event and physical result field, all recorded
ACT/PRE/RD/REF commands with addresses/timestamps across 128 domains, and the
ordered endpoint mutations and flit/VC/router-path trace. Native router/credit
algorithms are unchanged. Each side reads 9,439,488 native atoms. The complete
physical records and integer-ps drain times match. Only source/native/config file
identities and Python runtime fingerprints are excluded from the comparison.
These identity differences are retained separately.

Baseline source is `5536576`; optimized execution is
`47e68e5b5d26d499f3dc9dac06cbe2c29de805d2`. The optimized native binary was built
at `b80ea8f`; its build inputs match the frozen execution source. Existing relevant
unit/native regressions and small detailed equivalence checks also pass on hn072.
Evidence: [equivalence.json](../../artifacts/provenance/simulator_performance/equivalence.json).

## P2: isolate memory placement

All policies place the complete 128-expert catalog, including inactive experts.
They do not use evaluated routing, token choices or expert hotness. The reference
compute mapping is frozen independently of memory placement. Multi-layer initial
cache residency uses the same layer-0 objects, clusters, order and bytes in both
cases. No compute placement, tensor parallelism, context, SRAM, native domain,
HB, gateway or fabric resource changes are introduced.

The deterministic policies are:

- **Reference:** the existing grouped-modulo mapping.
- **Locality:** the nearest frozen consumer within its region; exactly the same
  layout as Reference, registered as an alias rather than another execution.
- **Balanced:** stripe the nine matrices of each expert partition across the four
  gateway groups in that region.
- **Hybrid:** retain Reference gate/up placement and rotate only down matrices
  across those groups by block index.

Physical address assignment and row locality can change with memory placement;
this is a memory-layout comparison, not an isolated gateway scheduling change.
Capacity checks cover the entire catalog. Screening reports necessary resource
work bounds and planned-route proxies; it does not predict application runtime.
Actual traffic below comes from native BookSim hops.

## P3: cold locality versus balance

All three full executions pass independent graph, storage, command/ACK, operand,
resource and drain audits. All read 151,031,808 native bytes and execute the same
490 tasks. The Locality alias was not rerun.

| Layout | Hottest-domain interface bound | Hottest-gateway payload bound | Remote weight payload | Actual hop-flits | Makespan |
|---|---:|---:|---:|---:|---:|
| Reference | 415.931 µs | 442.476 µs | 0 B | 52,536 | 581.384 µs |
| Balanced | 292.693 µs | 311.372 µs | 100,687,872 B | 1,167,416 | 582.050 µs |
| Hybrid | 369.721 µs | 393.312 µs | 33,562,624 B | 418,356 | 562.863 µs |

Balanced reduces the gateway maximum/mean load from 1.500 to 1.056, but is
0.115% slower. Hybrid has a ratio of 1.333 and reduces completion by **3.186%**.
Thus the most uniform layout is not the fastest in this input. Reduced native
and gateway work bounds compete with increased horizontal weight transport and
finite request/return feedback. Bounds and opportunity counters cannot allocate
the observed runtime difference into additive component stalls.

Last native/vertical tail readiness is 578.750480 / 579.479920 / 560.157280 µs;
it tracks the layer finish closely. The hottest receive write service is
114.345 / 116.667 / 115.119 µs. Global middle-cut payload is unchanged because
all moved weights stay within their original physical region. Neither a larger
global cut budget nor extra physical memory parallelism was added.

Execution source is `47e68e5`; selection analysis is `9d0ec5d`, with additional
executed pressure/cut analysis at `ecab49f` on the same immutable raw records.
[Cold analysis](../../artifacts/provenance/static_placement/cold-analysis.json) and
[cold registration](../../artifacts/provenance/static_placement/cold-registration.json)
retain result/input hashes, resource counters and screening values.

### What the executed records can explain

| Observation | Reference | Balanced | Hybrid |
|---|---:|---:|---:|
| Intra-reticle hop-flits | 34,980 | 1,149,860 | 400,800 |
| Cross-reticle hop-flits | 17,556 | 17,556 | 17,556 |
| Largest regional directed-cut work bound | 4.579 µs | 47.551 µs | 19.473 µs |
| Busiest channel mean lane service | 1.13% | 9.96% | 3.97% |
| Native read row conflicts | 150,636 | 158,800 | 153,551 |
| Mean native-controller read latency | 32.351 ns | 32.518 ns | 32.428 ns |
| Largest gateway queued payload | 544 B | 576 B | 576 B |

Cuts are reconstructed from actual directed-channel counters and physical router
positions. Their work bound divides data-lane bytes by the crossing channels'
declared rates. It includes traffic that actually crossed, not a planned-route
estimate. It is an optimistic service reference, not a critical-path delay.
The extra traffic is region-local; mean occupancy does not establish sustained
fabric bandwidth saturation. All layouts have zero observed HOL-with-credit
opportunities under the existing ready-aware policy.

Balanced has 5.42% more row conflicts, but only 0.52% higher mean controller read
latency. Controller latency begins at native acceptance and excludes upstream
waiting; it cannot explain the whole application timeline. Native return-space
rejection attempts are zero in all cases. Queue rejection attempts and sums of
receive job waits are retained in the evidence, but are not unique stall cycles.

Hybrid preserves local gate/up matrices and moves only some down matrices.
Balanced also moves gate/up matrices, adding paths on the dependencies that
produce gated activations. That is a concrete difference between the policies,
consistent with a locality/feedback tradeoff; the current three executions do
not isolate each phase's causal contribution. The modest cold gain warrants the
registered multi-layer check rather than a claim of universally optimal balance.

## P4: registered multi-layer confirmation, running

Hybrid was selected using only the completed cold results. Reference and Hybrid
are now executing the same 24-token, two-layer FFN-only sequence with a finite
184 MiB weight-cache partition inside each 192 MiB cluster SRAM. Both use two
shared-service contexts, contiguous-prefix operands, physical request/ACK,
refresh and the same initial layer-0 preload. Preload is outside measurement.
The two complete expert catalogs occupy 4.501 GiB, exceeding 3 GiB physical SRAM.

The execution source remains `47e68e5`. The minute monitor uses `dd69634` and
will run independent analysis after both completions; it does not automatically
retry failures. Registration is evidence of a frozen experiment, not a result.
No multi-layer improvement, equal miss count or reload amount is claimed here.
Zero reload is accepted as a valid observation. This new prefix study is separate
from the historical byte-count two-layer result.

Archive root: `/Projects/haoning/w2w-full-system-performance-placement-20261010`.
Raw native commands, results, builds and logs remain outside Git. See
[multi-layer registration](../../artifacts/provenance/static_placement/multilayer-registration.json)
and [run inventory](../../artifacts/provenance/static_placement/run-inventory.json).

Ideal global RX reservation, aggregate SRAM banking and assumed native array
timing remain model conditions. These measurements do not establish silicon
accuracy, complete Transformer behavior, stationary inference or product PPA.
