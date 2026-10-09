# W2W Memory-on-Logic

Develop and inspect source locally. Run builds, tests and experiments on
`hn072@143.89.78.72` under an isolated `/Projects/haoning/w2w-full-system-*`
directory. The user retired eex005 from new experiments on 2026-10-09; use it
only for evidence inventory, migration and verified cleanup.

Maintain `main`, synchronize committed source through Git, and preserve other
developers' work. RTL and `/Projects/haoning/wafer_simulator` have separate
owners; do not modify or delete their working directories. Keep credentials,
raw captures, native builds and environments out of Git.

Keep every project modification to simulator tools in this repository, including
native BookSim patches/runtime and DRAM extensions. New runs use the bundled
BookSim interface; use `tools/build_native.py` to build into an isolated external
directory. Unmodified third-party dependencies may be fetched at recorded pins.

The current architecture and execution contracts are in `docs/ARCHITECTURE.md`
and `docs/SIMULATOR.md`; `docs/HANDOFF.md` is the current task/status source.
Architecture V3 uses an independent physical stack and explicit mapping with the
existing unified kernel and native tools. Historical commands are recovered from
frozen tags. Do not replace the kernel, expand component acceptance campaigns,
or promote read-only subsystem results to full application timing.
