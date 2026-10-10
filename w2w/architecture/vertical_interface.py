"""Vertical lanes, logic gateways and external I/O are separate resources."""
from dataclasses import dataclass


@dataclass(frozen=True)
class VerticalPort:
    id: str
    region_id: str
    position_um: tuple[int, int]
    domain_ids: tuple[str, ...]
    gateway_id: str
    data_bits: int
    period_ps: int = 3760
    control_bits: int = 64
    hb_sites: int = 0
    landing_pitch_um: int = 4
    control_period_ps: int = 1000

    @property
    def landing_bounds_um(self):
        from math import ceil,isqrt
        if type(self.landing_pitch_um) is not int or self.landing_pitch_um<1 or self.hb_sites<1:
            raise ValueError('HB needs a declared positive pitch/site inventory')
        columns=isqrt(self.hb_sites)
        if columns*columns<self.hb_sites:columns+=1
        width=columns*self.landing_pitch_um;height=ceil(self.hb_sites/columns)*self.landing_pitch_um
        x,y=self.position_um;left=x-width//2;bottom=y-height//2
        return (left,bottom,left+width,bottom+height)


@dataclass(frozen=True)
class MemoryGateway:
    id: str
    reticle_id: str
    position_um: tuple[int, int]
    router_id: str
    data_bytes_per_cycle: int
    staging_bytes: int
    descriptor_slots: int
    control_bits: int = 64
    cdc_cycles: int = 2
    router_access_cycles: int = 0


@dataclass(frozen=True)
class ExternalPort:
    id: str
    position_um: tuple[int, int]
    router_id: str
    data_bytes_per_cycle: int
    staging_bytes: int
    descriptor_slots: int
    control_bits: int = 64


@dataclass(frozen=True)
class CollectionPath:
    id: str
    domain_id: str
    port_id: str
    gateway_id: str
    length_um: int
    data_bits: int = 128
    pipeline_cycles: int = 1
    period_ps: int = 3760

    @property
    def delay_ps(self): return self.pipeline_cycles*self.period_ps
