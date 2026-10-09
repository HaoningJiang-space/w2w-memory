"""Explicit candidate services; interface anchors do not imply controller policy or area."""
from dataclasses import asdict,dataclass
from math import ceil


@dataclass(frozen=True)
class RWDLInterface:
    arrays: int = 32
    bits_per_array: int = 128
    bytes_per_array: int = 16*1024**2
    period_ps: int = 3760


@dataclass(frozen=True)
class RWDLTiming:
    nBL: int = 1
    nCL: int = 2
    nRCD: int = 4
    nRP: int = 4
    nRAS: int = 9
    nRC: int = 13
    nWR: int = 4
    nRTP: int = 2
    nCWL: int = 2
    nWTR: int = 2
    nRTW: int = 2
    nRFC: int = 43
    nREFI: int = 1037


@dataclass(frozen=True)
class RWDLController:
    read_entries: int = 1
    descriptor_window: int = 1
    refresh_phase: str = 'synchronous'
    descriptor_policy: str = 'fifo'

    def __post_init__(self):
        if (type(self.read_entries) is not int or not 1<=self.read_entries<=4
                or type(self.descriptor_window) is not int or not 1<=self.descriptor_window<=4
                or self.refresh_phase not in ('synchronous','staggered')
                or self.descriptor_policy not in ('fifo','round_robin','row_batched')):
            raise ValueError('Declared candidate supports 1..4 entries/window and explicit refresh phase')


@dataclass(frozen=True)
class RWDLAggregation:
    bytes_per_cycle: int = 256
    cdc_cycles: int = 2
    reserved_atoms_per_array: int = 8
    organization: str = 'folded_center_reference'


@dataclass(frozen=True)
class RWDLProfile:
    interface: RWDLInterface = RWDLInterface()
    timing: RWDLTiming = RWDLTiming()
    controller: RWDLController = RWDLController()
    aggregation: RWDLAggregation = RWDLAggregation()

    def __post_init__(self):
        if self.interface!=RWDLInterface():raise ValueError('This implementation retains the declared 32x128-bit/3760ps interface')
        if any(type(v) is not int or v<1 for v in asdict(self.timing).values()):raise ValueError('Positive integer array timings required')
        if self.timing.nBL!=1:raise ValueError('Fixed 16 B/3760 ps candidate retains one-cycle RD')
        a=self.aggregation
        if (a.bytes_per_cycle<16 or a.bytes_per_cycle%16 or a.cdc_cycles<0 or a.reserved_atoms_per_array!=8
                or a.organization!='folded_center_reference'):
            raise ValueError('Invalid finite aggregation contract')


@dataclass(frozen=True)
class ComputeService:
    macs_per_cycle: int = 4096
    vector_ops_per_cycle: int = 256
    period_ps: int = 1000
    weight_banks: int = 32
    weight_read_bytes_per_bank_cycle: int = 128
    sram_bytes: int = 2*1024**2
    external_read_bytes_per_cycle: int = 256
    external_write_bytes_per_cycle: int = 256

    def __post_init__(self):
        if any(type(v) is not int or v<1 for v in asdict(self).values()) or self.sram_bytes%self.weight_banks:
            raise ValueError('Positive integer service budgets and equal SRAM banks required')

    @property
    def weight_read_bytes_per_cycle(self):
        return self.weight_banks*self.weight_read_bytes_per_bank_cycle

    def cycles(self,macs,vector_ops,weight_bytes):
        return max(ceil(macs/self.macs_per_cycle),ceil(weight_bytes/self.weight_read_bytes_per_cycle))+ceil(vector_ops/self.vector_ops_per_cycle)

    def record(self):
        return dict(**asdict(self),weight_read_bytes_per_cycle=self.weight_read_bytes_per_cycle,
            bank_capacity_bytes=self.sram_bytes//self.weight_banks,
            weight_read_data_lanes=self.weight_read_bytes_per_cycle*8,
            policy='one weight/scale read pass per tile reused across tokens; MAC/read overlap, vector phase serial',
            supply_overlap='max(MAC cycles, weight/scale read cycles), then vector cycles',
            bank_ports='one modeled wide compute read plus independent external read and receive write; physical SRAM macro implementation uncalibrated',
            internal_activation_and_scale_processing='included in arithmetic throughput assumption; no separate microarchitecture validation',
            area_um2=None,energy_j=None,calibrated=False)


def effective_resources(spec,native,compute):
    """Authoritative effective resource inventory; excludes legacy routing-only HB labels."""
    cc=[asdict(l) for l in spec.links if l.kind!='HB']
    return dict(schema='w2w.effective-services.v1',cc_links=cc,
        cross_layer=[dict(memory=m.id,home=m.home_tile,data_lanes=native['data_lanes_per_memory'],
            period_ps=native['interface_period_ps'],rw_dl_and_hb_same_lanes=True,
            direction='shared bidirectional lanes; experiment reads only') for m in spec.memories],
        memory_service=native,compute_service=compute,
        routing_only_hb_labels_excluded=True,
        internal_distribution=dict(organization='folded_center_reference',array_positions_um=None,
            hb_landing_positions_um=None,wire_bit_mm=None,area_um2=None,
            scope='unresolved spatial implementation; cannot use this reference for attachment/area DSE'))
