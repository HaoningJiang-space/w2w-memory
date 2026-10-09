"""Regions, execution clusters and routers are distinct physical objects."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ReticleRegion:
    id: str
    origin_um: tuple[int, int]
    size_um: tuple[int, int]
    layer: str

    def contains(self, position):
        return all(o <= p <= o+s for o, s, p in zip(self.origin_um, self.size_um, position))


@dataclass(frozen=True)
class ComputeProfile:
    pe_count: int = 4096
    macs_per_pe_cycle: int = 4
    vector_ops_per_pe_cycle: int = 1
    sram_bytes_per_pe: int = 48*1024
    weight_read_bytes_per_pe_cycle: int = 8
    activation_read_bytes_per_pe_cycle: int = 8
    sram_write_bytes_per_pe_cycle: int = 8
    period_ps: int = 1000
    fabric_read_bytes_per_cycle: int = 128
    fabric_write_bytes_per_cycle: int = 128

    def __post_init__(self):
        if any(type(v) is not int or v < 1 for v in vars(self).values()):
            raise ValueError('Compute service requires positive integer budgets')

    @property
    def sram_bytes(self): return self.pe_count*self.sram_bytes_per_pe

    @property
    def macs_per_cycle(self): return self.pe_count*self.macs_per_pe_cycle

    @property
    def vector_ops_per_cycle(self): return self.pe_count*self.vector_ops_per_pe_cycle

    @property
    def weight_read_bytes_per_cycle(self): return self.pe_count*self.weight_read_bytes_per_pe_cycle

    def cycles(self, macs, vector_ops, weight_bytes):
        from math import ceil
        return max(ceil(macs/self.macs_per_cycle), ceil(weight_bytes/self.weight_read_bytes_per_cycle))+ceil(vector_ops/self.vector_ops_per_cycle)


@dataclass(frozen=True)
class ComputeCluster:
    id: str
    reticle_id: str
    position_um: tuple[int, int]
    router_id: str
    profile: ComputeProfile = ComputeProfile()


@dataclass(frozen=True)
class Router:
    id: str
    reticle_id: str
    position_um: tuple[int, int]
    port_budget: int = 5
    input_buffer_bytes: int = 32*1024
    injection_buffer_bytes: int = 64*1024
    cycles: int = 3
