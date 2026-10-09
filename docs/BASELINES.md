# Vertical access baselines

Central/distributed candidates share compute fabric, frozen all-expert content
and addresses, compute placement, copies, arithmetic, native service and cold reads.

| Per region | Central | Distributed |
|---|---:|---:|
| PEs / SRAM | 16,384 / 768 MiB | 16,384 / 768 MiB |
| Native domains / capacity | 32 / 2 GiB | 32 / 2 GiB |
| HB data lanes | 4,096 | 4 × 1,024 |
| Gateway output | 128 B/cycle | 4 × 32 B/cycle |
| Return storage | 128 KiB | 4 × 32 KiB |
| Descriptor slots | Shared 32 | 4 × 8 |
| Atom reservations | 64 per domain | 64 per domain |

The central gateway lands at the center and reaches one existing aggregate
router through a charged 64-cycle path. Distributed gateways land at the four
cluster/router points. Both pay coordinate-derived raw collection. Both use
128 B fabric cuts and 32 KiB input data buffers. Additional control resources are
recorded. This central attachment is a first candidate; optimized central fanout
has not been established.

The external reference uses the same compute/mapping and an off-wafer native
DRAM service proxy. Four 32 B/cycle interfaces attach to the nearest edge routers
and use the compute fabric. Assumed 20 ns external propagation, 64-cycle edge
access and finite staging are paid. Domain coordinates are address-partition
labels for this proxy, not an external memory floorplan. External DRAM/I/O costs
are separate. This does not quantitatively reproduce MemoryX or have equal cost
to vertical integration.

[Cerebras weight streaming](https://www.cerebras.ai/blog/announcing-the-cerebras-architecture-for-extreme-scale-ai)
motivates data-driven execution. Streaming GEMM is a common reference condition,
not a new invention. Experiments measure one cold layer, not warm SRAM residency
or whole-model inference. The layer's complete weight library fits in aggregate
3 GiB SRAM; these results do not establish a need for DRAM in repeated execution
of a single resident layer.
