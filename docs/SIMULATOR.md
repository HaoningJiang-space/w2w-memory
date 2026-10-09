# Execution contracts

One kernel owns integer-ps time, dependencies, SRAM, engine contexts, requester
outstanding and gateway descriptor pools. It advances to actual clock boundaries
and scheduled events. Native callbacks keep original timestamps. Receive events
are committed before returned credits can advance subsequent traffic.

Ramulator schedules ACT/PRE/RD/refresh. Every physical domain has one controller,
command queue and return budget, regardless of gateway/access-view count.
Both halves of each 32 B word map to different 16 B native addresses. Reservations
remain held through physical collection, CDC, finite output and payload readiness.
Four central address views share one 32-slot descriptor pool.

BookSim executes routing, arbitration and credit from the physical graph.
NI/reservation accounting resolves endpoint names to physical routers.
Cells carry an envelope, payload and finite 64-bit sideband. Field sizes derive
from real router/endpoint ID spaces, including more than 64 endpoints.
Local payload DMA has no NoC envelope and shares destination write service.

GEMMs receive scales first, then consume committed descriptors as data arrives,
bounded by arithmetic and compute-SRAM read budgets. Engine contexts remain held
while awaiting operands; arithmetic busy time and context occupancy are separate.
This is one context per aggregate cluster. Full matrix SRAM is still reserved.
Source tensor transfers consume fabric-facing SRAM read service. No reduction
in weight staging is claimed.

Independent audits check transaction identity/order, tensor delivery, available
operands, per-cycle arithmetic/read service, engine occupancy, physical capacity,
finite reservations, gateway/MC pools and drain. Link-slot conservation is checked
online using actual native hops; offline analysis checks traffic capacity totals.

Receive booking is an ideal instantaneous reference. Native injection retains
its FIFO policy and one VC; unsupplied-head/ready-behind counts are reported.
Command-control wiring, fine SRAM conflicts, routing colors, multicast, power
constraints and controller area are not physically calibrated. The explicit
coordinate-derived propagation model covers returned data. It does not close
all command/control paths. Those assumptions accompany every interpretation.
