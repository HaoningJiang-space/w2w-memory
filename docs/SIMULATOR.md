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
bounded by arithmetic and compute-SRAM read budgets. The default `byte_count`
policy counts all committed data bytes and assumes aggregate out-of-order weight
consumption; it does not implement address-indexed activation/partial-sum hardware.
The optional `contiguous_prefix` policy consumes only the committed matrix prefix
in increasing byte-offset order. Its canonical fragment is one memory descriptor,
not one native atom or NoC cell. A validity bitmap and 64-bit frontier/association
are reserved within task SRAM and released at task completion; cache hits become
fully ready after the normal finite lookup. Independent audits reconstruct
physical descriptor offsets, reject overlapping deliveries, and enforce the
selected readiness contract. Prefix-hole observations count task/clock
opportunities and are not additive critical-path stall time.

Engine contexts remain held
while awaiting operands; arithmetic busy time and context occupancy are separate.
The default is one context per aggregate cluster. A declared finite 1–8 context
policy can overlap waiting contexts, with one shared arithmetic/read grant per
cluster cycle and 64 B extra scheduler state per added context inside SRAM.
Context occupancy is summed across slots. Full matrix storage is still reserved.
Source tensor transfers consume fabric-facing SRAM read service. No reduction
in weight staging is claimed.

Independent audits check transaction identity/order, tensor delivery, available
operands, per-cycle arithmetic/read service, engine occupancy, physical capacity,
finite reservations, gateway/MC pools and drain. Link-slot conservation is checked
online using actual native hops; offline analysis checks traffic capacity totals.

Receive booking is an ideal instantaneous reference. Native injection defaults to FIFO and one VC. Optional bounded oldest-admitted-among-ready
selection pays 96 bits/message and retains one physical cell/source/cycle; no
router or credit service is duplicated. Monotonic admission IDs set the priority,
not the time that data became ready. Opportunity counts are not additive stall.

Optional request control sends a 16 B range command per participating physical
domain, over shared 32-bit forward/32-bit reverse HB control at the logic clock.
Router-to-gateway access, coordinate-derived domain propagation, HB registration
and CDC are paid. A local domain frontend expands atoms into the existing native
controller. Range credits remain held through an 8 B serialized ACK. Central and
distributed total TX/ACK state match (16 KiB each); domain frontends pay 64 KiB.
This first protocol supports one owning gateway/domain and no external I/O;
receive booking is still ideal. Array timing/power, fine SRAM conflicts, routing
colors, multicast and control/selection area are not physically calibrated.

A finite matrix LRU weight cache can reserve a declared partition within existing
SRAM. Tag lookups use one finite serialized port; fills and consumers pin entries.
Misses use the existing DRAM/receive write path; hits share compute SRAM and MAC
service. Initial residency is explicit and its preload bytes are reported outside
the warm interval. Whole-layer warm behavior and capacity reloads require separate
workload identities. No streaming-buffer-only weight storage is claimed.
