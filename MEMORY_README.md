# Memory-on-Logic gates

This extension reuses the geometry at upstream commit `9470042` and adds direct
compute-to-memory service bounds. It does **not** turn a memory reticle into a
transit router, simulate DRAM timing, or establish a manufacturable bank layout.

## Reproduce

Python 3.11+ is recommended. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-memory.txt
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m unittest -v test_memory_model
OPENBLAS_NUM_THREADS=1 .venv/bin/python run_gate0.py --output memory_results/gate0.json
OPENBLAS_NUM_THREADS=1 .venv/bin/python run_memory_experiment.py --output memory_results --seeds 10
```

Every result stores the commit, working-tree status, hostname, Python and package
versions. Gate 0 writes progress after each topology. Do not claim a full
cycle-accurate reproduction: this gate checks only Table 1 topology metrics.

## Gate 0 conventions

The fixture is transcribed from [Table 1](https://arxiv.org/html/2603.05266v1).
All 24 original configurations are reconstructed, without reading cached metrics.
The four Interleaved LoI designs have actual maximum compute neighbor count 3;
the paper lists nominal radix 4. Upstream `plots.py:create_overview_table` supplies
radix using a hardcoded method dictionary. Both values are preserved in the audit.
Mean compute-to-compute hop count includes self pairs to match upstream.

Upstream adjacency extraction adds reverse edges even though neighbor information
already contains both directions. It therefore duplicates entries. Its raw cut
count happens to be numerically comparable to TB/s when a unique link has 2 TB/s.
We retain the original estimator and independently report deduplicated cuts times
2 TB/s. Do not multiply the upstream reported cut by another factor of two.
METIS partitions are heuristic: ten seeds need not reproduce a paper mean exactly.

## Gate 1 physical comparison

`integration_level="memory_and_logic"` is accepted by the existing constructor.
`aligned`, `half_shifted_x`, and `half_shifted` use the same compute locations,
number of memory reticles, area, and four-port reticle templates. A shared
rectangular footprint reserves space for the largest shift; it is deliberately
not the maximum utilization placement. This yields 12+12 reticles at 200 mm and
is recomputed for 300 mm. Memory centers move by (0,0), (13,0), or (13,16.5) mm.

`rotated` reuses the upstream geometry as an exploratory comparison. Its reticle
counts and areas differ, so it must not be interpreted as a resource-matched
speedup against the first three designs. DRAM bandwidth/capacity scale with memory
area relative to 26x33 mm; HB and controller provisioning remain per reticle.

Each wafer repeats the same shape and connector template. Geometry validation
checks containment, same-wafer overlaps, connector containment and repeated
geometry with bounded floating-point tolerance. Regions represent interface
placement areas, not fully populated bond-pad arrays. The current model assumes
compatible pad layout within each overlap; it does not perform pad-level alignment.

Each endpoint provisions a fixed total HB budget. For overlap e connecting
compute port p to memory port q:

```
link_bw[e] = min(C_HB / C_ports * overlap_area / C_port_area,
                 M_HB / M_ports * overlap_area / M_port_area)
```

An unbonded port loses bandwidth. Splitting one port across neighbors does not
multiply its provisioning. All links also share explicit per-port constraints.

## Gate 2 semantics and bounds

The default illustrative budgets are 4 TB/s compute HB, 4 TB/s memory HB,
4 TB/s compute controller, 1 TB/s memory-reticle DRAM service, and 16 GiB per
full-size memory reticle. These are sweep parameters, **not measured hardware**.
TB/s is decimal; GiB is binary. Only read data service is modeled.

* `partitioned`: each memory port owns an equal, disjoint bank group. A compute
  can access only the bank groups on the ports it overlaps. Each group owns
  1/port_count of the memory bandwidth and capacity.
* `pooled`: any port can address all banks in that memory reticle. Total DRAM
  bandwidth remains shared. A port can serve at most `pool_port_fraction` of
  the total (swept over 0.25, 0.5, 1). Full pooling is an optimistic bound,
  requiring a memory-internal selection/data network and multi-requester
  arbitration. This hardware is not free and has not been designed here.

The linear program maximizes either aggregate service or a common serviced
fraction of the positive demands. Constraints bound each controller, physical
link, HB port, DRAM reticle and bank-group/pooled port. It never forwards through
memory. `allowed_memories` optionally restricts data affinity (covered by tests);
the main sweep assumes data can be placed freely in reachable memory.

Sweeps cover 200/300 mm, four placements, both bank semantics, HB budgets
1/2/4/8 TB/s, controllers 1/4 TB/s, full/single/clustered/scattered activity,
10 random seeds, and both throughput and fairness objectives. Demand is 4 TB/s
per active compute. Shared capacities must not be summed across compute nodes.
Structural graph diameter describes the overlap graph only; legal memory
accesses are one edge, and unreachable accesses remain unsupported.

The output is a fluid bandwidth upper bound. No nanosecond latency, row buffers,
refresh, finite buffers, reads/writes arbitration, migration time, storage
allocation, thermal, yield, PDN or hardware cost is simulated. Throughput gain
under ideal data placement is not yet application speedup or evidence of locality.

## Research interpretation

The key test is whether geometry gains survive constrained bank access and equal
budgets. In a four-quadrant template, shifting an interior compute from one whole
memory to four independent quarter memories preserves its capacity and bank
bandwidth. Radix rises from 1 to 4 without increasing those resources. Pooling
can instead expose idle bank service under sparse activity, if HB/controller and
memory-internal port bandwidth allow it. Full wafer load and boundary loss are
necessary negative controls.

A promising next experiment must demonstrate a realizable, limited-cost bank
sharing interface, then use capacity-constrained page/bank placement and memory
request traces. Reject a claim whose gains exist only with free full-reticle
pooling. Do not infer unavoidable reticle mismatch or a global memory network.

Sources: [original paper](https://arxiv.org/html/2603.05266v1),
[original code](https://github.com/spcl/nw-design-for-wsi),
[SeDRAM research](https://doi.org/10.3390/electronics12051077), and
[memory/logic WoW patent disclosure](https://patents.google.com/patent/US20240420757A1/en).
The latter two motivate explicit bank/periphery interfaces; neither validates the
cross-reticle pooled architecture assumed by this experiment.
