# W2W Memory-on-Logic

Develop and inspect source locally. Run builds, tests and experiments on
`hn072@143.89.78.72` under an isolated `/Projects/haoning/w2w-full-system-*`
directory. The user retired eex005 from new experiments on 2026-10-09; use it
only for evidence inventory, migration and verified cleanup.

Maintain `main`, synchronize committed source through Git, and preserve other
developers' work. RTL and `/Projects/haoning/wafer_simulator` have separate
owners; do not modify or delete their working directories. Keep credentials,
raw captures, native builds and environments out of Git.

The current task is in `docs/handoff/NEXT_TASK.md`: deliver complete routed MoE
layer timing with existing native BookSim and DRAM components. Do not replace
the kernel, expand component acceptance campaigns, or promote read-only
subsystem results to full application timing.
