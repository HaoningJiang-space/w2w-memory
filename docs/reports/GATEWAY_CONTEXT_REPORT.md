# Finite compute contexts and a ready-aware central baseline

The frozen one-token V3 workload completes in **778.161 µs** with central FIFO,
**780.721 µs** with Central+, and **580.456 µs** with distributed FIFO. Independent
raw-event audits pass. Distributed reduces completion time by **25.41%** against
the two-context central FIFO and **25.65%** against Central+.

These are new execution-policy results, not replacements for the archived
843.182 / 581.749 µs one-context comparison.

| Policy | Completion (µs) | Hop-flits | Ready-behind with credit (source×cycles) | Last array beat tail (µs) |
|---|---:|---:|---:|---:|
| Central, two contexts, FIFO | 778.161 | 1,463,556 | 1,272,013 | 775.537600 |
| Central+, two contexts, finite ready-aware | 780.721 | 1,463,556 | 0 | 778.060560 |
| Distributed, two contexts, FIFO | 580.456 | 52,536 | 4,174 | 577.833040 |

Two contexts reduce central completion by 7.71% and distributed completion by
0.22% relative to the frozen one-context executions. Arithmetic, compute SRAM
read width, receive write width and total SRAM are unchanged. Each additional
waiting context pays 64 B scheduler state inside SRAM; input/output/scratch and
matrix storage retain their existing reservations. At most **one** ready context
receives the cluster's shared arithmetic/read grant in each compute cycle.
This is a finite aggregate execution policy, not a calibrated model of a
commercial processor's contexts/register files. `engine_context_ps` now sums
slot occupancy and can exceed elapsed time; it is not arithmetic utilization.

Central+ adds 16 oldest-admitted-among-ready entries to each of four central injection sources,
96 bits/entry: **6,144 bits (768 B)** of selector state. It adds no data buffer,
physical injection port, MAC service, SRAM read bandwidth or HB data lanes.
One selected cell can inject per source clock; BookSim's router, VC, arbitration
and credit machinery remain unchanged. Selector logic area and timing closure
are not calibrated.
The frozen metadata called this "oldest-ready". Its actual priority is the
smallest monotonically assigned admission ID among supplied messages, not the
earliest data-ready timestamp. This naming correction changes no scheduling.

The source intervention removes the observed ready-behind condition but slows
completion by **0.329%**. Native readiness also moves later. This is a closed-loop
application result: injection order changes outstanding release and subsequent
DRAM requests. A HOL opportunity counter is not an independently additive stall
or a prediction of application benefit. Neither context overlap nor this finite
selector explains away the distributed advantage on this input.
This result does not establish that other ready-aware priority policies have
no benefit.

The comparison still changes physical collection, injection location, local
queues/pools and horizontal return paths together. It does not isolate HB
landing position or establish that distributed beats a costed central fanout.
Request-control transport remains disabled in this particular intervention so
that it can be compared to the historical execution contract. The later
memory-hierarchy study enables finite physical range commands and ACK credits
and must retain its separate identity.

## Reproduction and evidence

Execution source: `13719f058b37795a66a217a9e3d4df3cc51a4b8c`.
BookSim SHA-256: `0d38604f6904305da3975b0b817ad3a1e469189150fb987ac6d84734ba70238b`.
Ramulator upstream: `72427a1bba3771564c4fb0e494ba02242fd1eaa7`.
Bridge SHA-256: `37eb00768993fb5cfd903c690e72a21cdc69e10f4acbc421762f54dc5a33ba54`.

Each case has 490 tasks, 37,152 descriptors, 151,031,808 native bytes and the same
registered graph/placement. The native configuration hash and physical compute,
SRAM, native service, fabric, HB data, gateway output/staging/descriptor budgets
match. Distributed pays additional port/control resources, reported separately.

Selected identities, completion records and independent analysis are in
[`artifacts/provenance/gateway_context`](../../artifacts/provenance/gateway_context/).
Large frozen inputs/raw captures and build manifests are at
`hn072:/Projects/haoning/w2w-full-system-gateway-cache-20261009/context-study-r2`;
the sibling `context-evidence-sha256.json` indexes their bytes and SHA-256.

```sh
python -m w2w run_gateway_baseline --prepare --compute-contexts 2 --output NEW_DIRECTORY
python -m w2w run_gateway_baseline --output NEW_DIRECTORY --case central-plus --booksim-binary BINARY
python -m w2w.analysis.gateway_hierarchy --source COMPLETED_DIRECTORY --output ANALYSIS_JSON
```

The input is one cold routed FFN layer. Ideal instantaneous receive booking,
candidate array timing, coarse fabric aggregation, internal SRAM banking and
uncalibrated controller/selection area remain limitations. This result does not
establish a steady-state LLM benefit or calibrated wafer PPA.
