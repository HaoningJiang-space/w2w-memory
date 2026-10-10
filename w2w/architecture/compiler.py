"""Architecture lowering targets the existing unified kernel, not a second executor."""
from dataclasses import dataclass,asdict
from functools import cached_property
from types import MappingProxyType
from .resources import inventory,cell_format


@dataclass(frozen=True)
class ExecutionCluster:
    id: str
    reticle: str
    x: int
    y: int
    sram_bytes: int
    compute_period_ps: int
    router_id: str


@dataclass(frozen=True)
class MemoryInterface:
    id: str
    home_tile: str  # gateway's physical router, not an implicit compute owner
    banks: int
    capacity_bytes: int
    transaction_slots: int
    domain_ids: tuple
    gateway_id: str
    mc_pool_id: str


@dataclass(frozen=True)
class ExecutableChannel:
    id: str
    src: str
    dst: str
    kind: str
    resource_id: str
    width_bits: int
    period_ps: int
    pipeline_cycles: int
    credit_cycles: int
    length_um: int
    segments: tuple


@dataclass(frozen=True)
class ExecutableMachine:
    stack: object
    tiles: tuple
    memories: tuple
    links: tuple
    routers: tuple
    baseline: str = 'V3'
    allow_stitching: bool = True
    noc_period_ps: int = 1000
    flit_bytes: int = 128
    router_cycles: int = 3
    input_buffer_flits: int = 256
    injection_flits: int = 512
    ejection_packets: int = 16
    packet_payload_bytes: int = 4096
    header_bytes: int = 16
    outstanding_per_tile: int = 32
    dram_period_ps: int = 3760
    rx_write_bytes_per_cycle: int = 128
    read_requests_per_tile_cycle: int = 2
    memory_request_bytes: int = 4096

    @cached_property
    def endpoint_routers(self):
        return MappingProxyType({**{r.id:r.id for r in self.routers},
            **{c.id:c.router_id for c in self.tiles},**{m.id:m.home_tile for m in self.memories}})

    def endpoint_router(self, key):
        try:return self.endpoint_routers[key]
        except KeyError:raise ValueError('Unknown physical endpoint') from None


def compile_machine(stack):
    domains={d.id:d for d in stack.dram_domains}
    gateways={g.id:g for g in (*stack.gateways,*stack.external_ports)}
    xs=sorted({c.position_um[0] for c in stack.compute_clusters})
    ys=sorted({c.position_um[1] for c in stack.compute_clusters})
    tiles=tuple(ExecutionCluster(c.id,c.reticle_id,xs.index(c.position_um[0]),
        ys.index(c.position_um[1]),c.profile.sram_bytes,c.profile.period_ps,c.router_id)
        for c in stack.compute_clusters)
    memories=tuple(MemoryInterface(g.id,gateways[g.gateway_id].router_id,len(g.domain_ids),
        sum(domains[d].capacity_bytes for d in g.domain_ids),g.mc_slots,g.domain_ids,
        g.gateway_id,g.mc_pool_id) for g in stack.bank_groups)
    links=tuple(ExecutableChannel(c.id,c.src,c.dst,'compute_fabric',c.id,c.data_bits,
        c.period_ps,c.channel_cycles,c.channel_cycles,c.length_um,c.segments) for c in stack.lateral_links)
    machine=ExecutableMachine(stack,tiles,memories,links,stack.routers)
    if any(r.cycles!=machine.router_cycles for r in stack.routers):
        raise ValueError('First native compiler supports uniformly declared three-cycle routers')
    if len({c.profile.period_ps for c in stack.compute_clusters})!=1:
        raise ValueError('First aggregate backend requires one compute/fabric clock')
    if any(r.input_buffer_bytes != machine.input_buffer_flits*machine.flit_bytes or
           r.injection_buffer_bytes != machine.injection_flits*machine.flit_bytes for r in stack.routers):
        raise ValueError('Router buffer budgets do not match executable reservoir')
    if any(c.data_bits!=machine.flit_bytes*8 or c.period_ps!=machine.noc_period_ps for c in stack.lateral_links):
        raise ValueError('No implicit SerDes or fabric CDC')
    if cell_format(len(stack.routers),machine.flit_bytes,endpoint_count=len(tiles))['sideband_bits']>min(c.control_bits for c in stack.lateral_links or [type('Local',(),{'control_bits':64})()]):
        raise ValueError('Cell metadata exceeds declared control path')
    return machine
