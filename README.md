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

The first matched, cold, one-token routed FFN comparison completes in
**843.182 µs with central vertical access and 581.749 µs with distributed access**:
31.006% lower completion time. Both read 151,031,808 B through the same 128 native
domains, compute placement and arithmetic plan. The raw collection wire proxy
falls by 50%; extra gateway/control resources are recorded. These are candidate
machine results and resource proxies. See [the report](docs/reports/ARCHITECTURE_V3_REPORT.md).

Builds, tests and execution run in isolated directories on `hn072`; edit source
locally and synchronize committed revisions through Git. No sibling simulator
checkout is needed. From the repository root on the execution host:

```sh
python tools/build_native.py --tool all --output /absolute/new/native-build
export W2W_BOOKSIM_BINARY=/absolute/new/native-build/booksim/endpoint_booksim
export W2W_RAMULATOR_BRIDGE=/absolute/new/native-build/dram_bridge/_w2w_ramulator.cpython-310-x86_64-linux-gnu.so
export PYTHONPATH=/absolute/new/native-build/ramulator2/python
python -m w2w compile_machine --organization distributed --output /absolute/new/machine
python -m w2w run_vertical_access --prepare --cases central distributed --output /absolute/new/study
python -m w2w run_vertical_access --case central --output /absolute/new/study
python -m w2w run_vertical_access --case distributed --output /absolute/new/study
python -m w2w analyze_vertical_access --source /absolute/new/study --output /absolute/new/analysis.json
```

Native builds require CMake, C++, make, flex, bison, Python development headers
and the pinned upstream Ramulator Python package. Reuse a built pinned upstream
with `--ramulator-source` and point `PYTHONPATH` to its Python package. Build and
result directories remain outside the source checkout.

[Architecture](docs/ARCHITECTURE.md), [physical assumptions](docs/PHYSICAL_ASSUMPTIONS.md),
[simulator contracts](docs/SIMULATOR.md), [baselines](docs/BASELINES.md),
[source map](docs/CODE_STRUCTURE.md) and [handoff](docs/HANDOFF.md) describe the
current platform. `python -m w2w --help` lists the three current entrypoints.

Historical V2 commands/results are available at `v2-frozen-37400e6` and the
separate cost-study tags. [The freeze inventory](docs/legacy/V2_FREEZE.md) records
source, binary and server archive identities. V2 results remain V2 evidence.
[Software provenance](docs/legacy/SOFTWARE_PROVENANCE.md) preserves reused code
origins and licenses. `rtl/` is independently owned and unchanged; it does not
execute in V3. `wafer_simulator` remains an independent project.
