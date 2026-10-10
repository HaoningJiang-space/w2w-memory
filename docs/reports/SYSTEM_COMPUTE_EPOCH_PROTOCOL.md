# First system compute epoch

Registered candidate, not an application speedup receipt. Keep the existing V3
kernel, full-activation start rule, per-consumer unicast, physical machine,
BookSim and Ramulator. The switch defaults off. No G2.2/G2.3 or multicast backend
is introduced by this experiment.

This first transition requires one running streaming context, all weight and
scale bytes committed, no live task read/transport/control/MC reservations, and
an explicit quiescent-memory capability. It stops before releases, the explicit
deadline and the final possibly short service. Observers and cache execution
disable the transition. A second context or active network credit disables it.
Compute and NoC clocks must match; integer-ps phases remain absolute.

The host jumps a certified compute-only interval. On resumption Ramulator's
ordinary advance executes every omitted internal DRAM clock, including refresh.
Only an already drained BookSim can use its existing idle synchronization. No
active router, credit, command or data-return sequence is approximated. This is
not yet an interactive DRAM/Gateway/NoC/Compute macro.

Full recording produces original per-cycle compute rows without running kernel
arbitration per row. Compact recording stores a versioned constant-service
interval. The independent `validation.compute_epoch` reader expands it; the
existing system/vertical/control audits then verify availability, service,
task finish, capacities and drain. Compact results require expansion before
these full audits. Native command and endpoint fingerprints must be equal.

Run new tests and fixed small native comparisons on hn072 in a fresh
`/Projects/haoning/w2w-full-system-compute-epoch-*` workspace. Record source,
input, interpreter, native binary/bridge/environment and raw artifact hashes.
Compare off/full/compact on the same source and physical inputs; report kernel
iterations separately from emitted records and full worker costs. Reuse a native
build only after matching its build-input identities; otherwise build using
`tools/build_native.py` into this isolated workspace.

Accuracy cases: a slow streaming GEMM, a short/partial final service, an external
task release between compute clocks, and a transport-heavy streaming GEMM that
may have little safe coverage. Native refresh remains enabled. No timing-out
case is accepted. Preserve failed attempts and use fresh output directories.

Fabric abstraction is a separate machine-policy question. Current aggregation
does not model routing colors or multicast. A future comparison must explicitly
account for branch copies, shared-path service, finite buffers and consumer
readiness while preserving DRAM/HB/gateway/compute budgets. No free multicast or
architecture-order stability is inferred from this behavior-preserving test.
