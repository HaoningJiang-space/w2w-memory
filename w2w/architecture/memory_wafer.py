"""Physical native service identity is independent of its access interfaces."""
from dataclasses import dataclass


@dataclass(frozen=True)
class DRAMDomain:
    id: str
    region_id: str
    position_um: tuple[int, int]
    capacity_bytes: int = 64*1024**2
    data_bits: int = 128
    period_ps: int = 3760
    command_read_entries: int = 4
    return_atoms: int = 8


@dataclass(frozen=True)
class MemoryBankGroup:
    """Address-space view; overlapping views do not create physical capacity."""
    id: str
    domain_ids: tuple[str, ...]
    gateway_id: str
    mc_pool_id: str
    mc_slots: int


@dataclass(frozen=True)
class NativePolicy:
    read_entries: int = 4
    descriptor_window: int = 4
    descriptor_policy: str = 'row_batched'
    refresh_phase: str = 'staggered'
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
    nRFC: int = 172
    nREFI: int = 1037

    def __post_init__(self):
        if self.read_entries not in (1, 2, 4) or not 1 <= self.descriptor_window <= 4:
            raise ValueError('Finite native request window required')
        if self.descriptor_policy not in ('fifo', 'row_batched', 'round_robin'):
            raise ValueError('Unknown native expansion policy')
        if self.refresh_phase not in ('synchronous', 'staggered'):
            raise ValueError('Explicit refresh phase required')
