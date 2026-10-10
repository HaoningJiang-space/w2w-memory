# W2W Memory Architecture

Architecture V3 studies vertical DRAM access for a distributed wafer-scale
compute fabric. Physical regions, compute clusters, routers, native DRAM domains,
HB ports and memory gateways have separate identities. Static workload mapping
is separate from the physical machine. The existing unified kernel executes
native BookSim and pinned Ramulator; it has not been replaced.

The first candidate models four physical regions, sixteen aggregate clusters,
65,536 candidate PEs, 3 GiB SRAM and 8 GiB DRAM. It uses public distributed-compute
architecture as a reference, with declared aggregate service assumptions.
It does not reproduce proprietary Cerebras microarchitecture or an existing
logic–DRAM wafer product.

The completed [operand-aware cold FFN pair](docs/reports/OPERAND_AWARE_ACCESS_REPORT.md)
takes **782.060 µs for Central+ and 581.384 µs for Distributed**, a 25.66%
completion reduction. Both use committed contiguous operands, finite selectors,
two shared-service contexts, command/ACK, refresh and the same graph, addresses
and native/data budgets. Additional control/layout costs are recorded, not
assumed equal PPA. Actual middle-cut traffic is identical; this primarily
changes region-local collection/injection and request feedback.

The completed [24-token two-layer finite-cache proxy](docs/reports/TWO_LAYER_CACHE_REPORT.md)
takes **15.030022 / 13.281470 ms**, reducing completion by 11.63%. Both read the
same native bytes and have identical invocation traffic counts. Token 12–23
still reloads 585,248,256 B. This study retains its frozen byte-count policy,
so it is separate from the prefix pair. The [whole-layer warm reference](docs/reports/WARM_LAYER_REFERENCE.md)
remains 658.065 µs and zero DRAM weight reads, with preload outside measurement
and accounted separately. These are FFN timing candidates, not complete
Transformer, calibrated silicon or product-PPA results.

The [independent RWDL probe](docs/reports/RWDL_SERVICE_DOMAIN_REPORT.md) verifies
exact addresses/commands and finite drain: 256 KiB takes 11.087 µs across eight
existing domains versus 84.779 µs on one. This is read-service parallelism,
not application acceleration. Original [V3](docs/reports/ARCHITECTURE_V3_REPORT.md)
and [context](docs/reports/GATEWAY_CONTEXT_REPORT.md) results retain their frozen
source/native identities; no historical result is overwritten.

The [simulator performance and static-placement study](docs/reports/SIMULATOR_PERFORMANCE_PLACEMENT_REPORT.md)
achieves **2.161× / 2.077× total wall-clock speedup** on matched full cold
Central+/Distributed gates, with identical physical events and integer-ps
results. With compute placement frozen, Hybrid memory placement improves cold
Distributed completion from **581.384 to 562.863 µs (3.19%)**; more uniform
Balanced placement takes 582.050 µs. The registered 24-token two-layer
Reference/Hybrid confirmation is running; it has no completed result yet.

Builds, tests and execution run in isolated directories on `hn072`; edit source
locally and synchronize committed revisions through Git. No sibling simulator
checkout is needed. From the repository root on the execution host:

```sh
python tools/build_native.py --tool all --output /absolute/new/native-build
export W2W_BOOKSIM_BINARY=/absolute/new/native-build/booksim/endpoint_booksim
export W2W_RAMULATOR_BRIDGE=/absolute/new/native-build/dram_bridge/_w2w_ramulator.cpython-310-x86_64-linux-gnu.so
export PYTHONPATH=/absolute/new/native-build/ramulator2/python
python -m w2w compile_machine --organization distributed --output /absolute/new/machine
python -m w2w run_operand_access --prepare --output /absolute/new/study
python -m w2w run_operand_access --case central-plus --output /absolute/new/study
python -m w2w run_operand_access --case distributed --output /absolute/new/study
python -m w2w analyze_operand_access --source /absolute/new/study --output /absolute/new/analysis.json
# Separate full-catalog memory-placement study; compute placement stays fixed.
python -m w2w run_static_placement --prepare --mode cold --output /absolute/new/placement
python -m w2w run_static_placement --case reference --output /absolute/new/placement
python -m w2w run_static_placement --case balanced --output /absolute/new/placement
python -m w2w run_static_placement --case hybrid --output /absolute/new/placement
python -m w2w analyze_static_placement --source /absolute/new/placement --output /absolute/new/placement-analysis.json
```

Native builds require CMake, C++, make, flex, bison, Python development headers
and the pinned upstream Ramulator Python package. Reuse a built pinned upstream
with `--ramulator-source` and point `PYTHONPATH` to its Python package. Build and
result directories remain outside the source checkout.

[Architecture](docs/ARCHITECTURE.md), [physical assumptions](docs/PHYSICAL_ASSUMPTIONS.md),
[simulator contracts](docs/SIMULATOR.md), [baselines](docs/BASELINES.md),
[source map](docs/CODE_STRUCTURE.md) and [handoff](docs/HANDOFF.md) describe the
current platform. `python -m w2w --help` lists the current entrypoints.

Historical V2 commands/results are available at `v2-frozen-37400e6` and the
separate cost-study tags. [The freeze inventory](docs/legacy/V2_FREEZE.md) records
source, binary and server archive identities. V2 results remain V2 evidence.
[Software provenance](docs/legacy/SOFTWARE_PROVENANCE.md) preserves reused code
origins and licenses. `rtl/` is independently owned and unchanged; it does not
execute in V3. `wafer_simulator` remains an independent project.
