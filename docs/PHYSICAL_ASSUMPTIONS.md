# Architecture V3 assumptions

V3 starts from a distributed compute wafer and adds a candidate memory layer.
The [Cerebras architecture description](https://www.cerebras.ai/blog/cerebras-architecture-deep-dive-first-look-inside-the-hw-sw-co-design-for-deep-learning)
provides anchors for local SRAM, datapath banking, fine message routing and short
boundary crossings. It does not specify this simulator's vertical DRAM machine.

The first machine has four 26 × 33 mm physical fields, each containing four
aggregate clusters. Each cluster represents 4096 PEs with 48 KiB SRAM per PE.
The totals are 65,536 PEs and 3 GiB SRAM. Four MACs/PE/cycle, 1 GHz, and the
FP8-to-arithmetic service assumption are candidate budgets, not WSE-3 specs.
SRAM supplies separate 8 B weight and 8 B activation reads per PE/cycle; the
external fabric receive path is 128 B/cluster/cycle. Macro bank conflicts and
numerical FP8 execution are not validated. No claim of area feasibility follows.

The field envelope follows the publicly documented
[ASML 26 × 33 mm exposure field](https://www.asml.com/en/products/duv-lithography-systems/twinscan-xt-1060k),
not the retired network artifact. The named recipe fixes field dimensions and
service ratios. Uncalibrated core/array/interface densities do not support an
area-optimization claim or arbitrary field shrinking with unchanged resources.

A 128 B macro channel represents 64 fine 16-bit data lanes. A separate 1024-bit
control cut pays for metadata. Intra-field and boundary macro paths represent
64 and 65 fine hops respectively; BookSim's three-cycle macro router is included
in those counts. The 100 µm boundary segment is distinct from the surrounding
13–16.5 mm intra-field paths. This aggregate timing policy is not a cycle-exact
implementation of Cerebras static colors, multicast or microthreading.

Each field has 32 independent native domains. The V3 capacity candidate is
64 MiB/domain (four times V2 rows), totaling 8 GiB. It retains a 128-bit/3760 ps
interface and explicitly changes refresh occupancy to nRFC=172, nREFI=1037.
This conservative capacity scaling is an assumed DRAM organization, not a
measured SeDRAM capacity/timing bin. Each domain has one shared command/data
service identity even if several access views or HB ports reference it.

Both vertical organizations pay raw-domain collection transport: Manhattan
distance from the domain's coarse grid position to the HB landing, one registered
stage per millimeter at the native clock, one HB beat, two logic CDC cycles and
the declared gateway-to-router access. This is a spatial sensitivity model, not
wire timing signoff. Finite atom reservations cover the entire transport.

There are 64 reserved 16 B atoms per physical domain, counted once across access
views, giving 32 KiB/region of native return capacity. Gateway return storage is
another declared 128 KiB/region. Controller command entries, finite cell metadata,
gateway-to-router wires and edge access resources are separately recorded.

The [TSMC 2025 annual report](https://investor.tsmc.com/sites/ir/annual-report/2025/2025%20TSMC%20Annual%20Report.E.pdf)
separately describes logic/DRAM WoW progress and wafer-scale system integration.
Those are technology motivations; they do not establish this combined machine
as an existing product. Wire, pipeline, buffer and control counts are proxies;
controller area, energy, yield and thermal behavior remain uncalibrated.

V2 evidence remains under its frozen Git tags. V3 has a new machine identity and
does not inherit V2 completion times or the old Network Design geometry model.
