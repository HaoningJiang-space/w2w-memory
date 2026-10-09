# Current handoff

P0–P6 source work is complete: V2 freeze, independent physical machine, direct
native topology export, workload/mapping separation, shared vertical service,
matched end-to-end comparison and legacy source removal.

The first full central/distributed comparison is frozen at a219300:
843.182 / 581.749 µs for the same one-token layer. Native/event audits pass.
The external case at a219300 was invalidated for attaching some edge interfaces
to interior routers. Corrected source b28a444 completed in 1459.319 µs in
`hn072:/Projects/haoning/w2w-full-system-v3-20261009/edge-study-v1`, with timed
monitoring; its independent analysis and native/event audits pass. Its external
I/O budget is separate from the matched vertical comparison.

Builds, migration checks, small complete FFNs, source audit and matched study
are under `/Projects/haoning/w2w-full-system-v3-20261009`.
[The report](reports/ARCHITECTURE_V3_REPORT.md) records identities; large captures,
builds and environments remain outside Git.

Use physical IR and explicit budgets for new designs. Central connection/fanout
and native source FIFO remain choices; two points do not establish an optimum.
Warm SRAM, fine multicast and numerical inference are separate work. No endpoint
RTL, dynamic placement or broad search was added.
