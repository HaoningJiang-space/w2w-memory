# Current source map

| Directory | Responsibility |
|---|---|
| `architecture/` | Physical stack, budgets, legal paths and compilation |
| `workloads/` | Logical operators, tensors and frozen token selections |
| `mapping/` | Residency, compute placement, explicit copies and addresses |
| `domain/` | Immutable execution/transaction records |
| `system/` | Single kernel, local DMA and shared receive writes |
| `backends/booksim/` | Physical export, native IPC, prefix supply and commit |
| `backends/ramulator/` | Command models, shared-domain adapter and bridge |
| `experiments/` | Compile, register, execute and save |
| `analysis/` | Read completed evidence |
| `validation/` | Independent event/resource audits |
| `configs/` | Candidate ratios, frozen workloads and recipe |
| `third_party/` | Pinned source, patches, provenance and licenses |
| `tools/` | Build, source-boundary audit and timed monitoring |

Python package directories above are under `w2w/`. Machine/workload/mapping do
not import retired geometry or runners. Native tools require no RapidChiplet
configuration or sibling simulator. `tools/audit_architecture_independence.py`
checks the boundary. Historical sources are restored from frozen Git tags.
The separately owned `rtl/` directory is unchanged and outside V3 execution.
