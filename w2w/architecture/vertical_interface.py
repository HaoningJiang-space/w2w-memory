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
