# Wafer-scale Memory Fabric

Research repository: [HaoningJiang-space/w2w-memory](https://github.com/HaoningJiang-space/w2w-memory).
This extension explores how repeated reticle geometry, nonuniform bank exposure,
HB bandwidth allocation and offline data layout jointly determine usable memory
flexibility. Service loss and physical proxies are reported as tradeoffs.

The objective remains **wafer-scale memory service fabric co-design**. Placement
determines physical paths, endpoint organization determines their service, and
static residency determines which resources each request must consume. Matching,
pooling and FIFO organization are tools at different layers, not successive topics.

Current integration fixes geometry and data layout, connects endpoint time/width
constraints to the bank/wafer LP, and checks complete-word finite-buffer execution.
This first bridge covers a disjoint full-bank pair design; it is not a general
wafer queue simulator or calibrated DRAM implementation.

- [Current endpoint-to-wafer integration results](ENDPOINT_BRIDGE_REPORT.md): 64 finite traces, 160 fixed-layout comparisons, independent pair checks.
- [Integration model and reproduction](ENDPOINT_BRIDGE_METHOD.md): explicit word storage, backpressure, serial time and composition limits.
- [Endpoint contracts and public digital interface boundary](ENDPOINT_CONTRACT_GATE.md).
- [Closed nonuniform search](NONUNIFORM_POOLING_REPORT.md): no stable aggregate advantage; distinct from the endpoint implementation question.
- [Physical question: bank/LIO endpoint to HB](BANK_HB_PHYSICAL_BOUNDARY.md): demonstrated interfaces, candidate freedoms and missing physical parameters.
- [Earlier partitioned/striped capacity check](SLICE_EXPOSURE_REPORT.md): 108 cases; striping benefit depends on native endpoint capacity, with parent bank limits retained.
- [Slice model and exact equivalence arguments](SLICE_EXPOSURE_METHOD.md).
- [Completed service-driven search and Gurobi ILP reference](SERVICE_DRIVEN_REPORT.md): frozen-layout validation, integer optimality scope and cost.
- [Earlier Memory Fabric DSE results](MEMORY_FABRIC_DSE_REPORT.md): 68 hardware candidates, relaxed service and frozen-layout comparisons.
- [Open Memory Fabric DSE method](MEMORY_FABRIC_DSE_METHOD.md): geometry, graph, widths and static layouts; 0/0.9/1 service profiles.
- [Guaranteed reciprocal reference results](GUARANTEED_EXCHANGE_REPORT.md): a reference family, not a restriction on the design space.
- [Earlier bounded-sharing Gate report](BANK_GATE_REPORT.md): partial pass; static-layout throughput benefits, with fairness and implementation-cost limitations.
- [Experiment method and reproduction](BANK_GATE_METHOD.md).
- [Related-work and claim-boundary audit](BANK_RELATED_WORK.md).
- [Original memory extension and reproduction](MEMORY_README.md).
- [Git workflow and local/eex005 synchronization](GIT_WORKFLOW.md).

Only `main` is maintained. Earlier Gates remain available in its commit
history; no separate research branches are needed. Working experiment directories
are excluded from Git; selected raw results, reports, figures and provenance are
versioned. [Server archive and recovery](SERVER_STORAGE.md).

## Upstream artifact

Based on [spcl/nw-design-for-wsi](https://github.com/spcl/nw-design-for-wsi),
retaining its history and original attribution below.

### Network Design for Wafer-Scale Systems with Wafer-on-Wafer Hybrid Bonding

This repository contains the artifacts accompanying the paper:

**“Network Design for Wafer-Scale Systems with Wafer-on-Wafer Hybrid Bonding.”**
