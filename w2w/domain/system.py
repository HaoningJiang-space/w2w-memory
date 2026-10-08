"""v2 physical resources. Explicit connected-compute platform; standard library only."""
from dataclasses import dataclass


def positive(value, name, minimum=1):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')


@dataclass(frozen=True)
class TileSpec:
    id: str
    reticle: str
    x: int
    y: int
    sram_bytes: int = 4096
    compute_period_ps: int = 1000

    def __post_init__(self):
        positive(self.sram_bytes, 'SRAM bytes')
        positive(self.compute_period_ps, 'compute period')


@dataclass(frozen=True)
class MemorySpec:
    id: str
    home_tile: str
    banks: int = 32
    capacity_bytes: int = 512 * 1024**2
    transaction_slots: int = 4

    def __post_init__(self):
        for key in ('banks', 'capacity_bytes', 'transaction_slots'):
            positive(getattr(self, key), key)
        if self.capacity_bytes % (32 * self.banks):
            raise ValueError('Capacity must contain whole 32-byte words per bank')


@dataclass(frozen=True)
class PhysicalLink:
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

    def __post_init__(self):
        if self.kind not in ('intra_reticle', 'stitch', 'HB'):
            raise ValueError('Unsupported physical link kind')
        for key in ('width_bits', 'period_ps', 'pipeline_cycles', 'credit_cycles'):
            positive(getattr(self, key), key)
        positive(self.length_um, 'length_um', 0)
        if self.width_bits % 8:
            raise ValueError('Byte-aligned flits required')


@dataclass(frozen=True)
class SystemSpec:
    tiles: tuple[TileSpec, ...]
    memories: tuple[MemorySpec, ...]
    links: tuple[PhysicalLink, ...]
    baseline: str = 'B1'
    allow_stitching: bool = True
    noc_period_ps: int = 1000
    flit_bytes: int = 16
    router_cycles: int = 1
    input_buffer_flits: int = 4
    injection_flits: int = 16
    ejection_packets: int = 2
    packet_payload_bytes: int = 64
    header_bytes: int = 16
    outstanding_per_tile: int = 4
    dram_period_ps: int = 1000
    ideal_dram_cycles: int = 5
    rx_write_bytes_per_cycle: int = 16
    read_requests_per_tile_cycle: int = 1
    memory_request_bytes: int = 32

    def __post_init__(self):
        for key in ('tiles', 'memories', 'links'):
            object.__setattr__(self, key, tuple(getattr(self, key)))
        if self.baseline not in ('B0', 'B1'):
            raise ValueError('Only B0/B1 are executable; Direct HB is not implicit')
        for key in ('noc_period_ps', 'flit_bytes', 'router_cycles', 'input_buffer_flits',
                    'injection_flits', 'ejection_packets', 'packet_payload_bytes',
                    'header_bytes', 'outstanding_per_tile', 'dram_period_ps', 'ideal_dram_cycles',
                    'rx_write_bytes_per_cycle', 'read_requests_per_tile_cycle', 'memory_request_bytes'):
            positive(getattr(self, key), key)
        if self.memory_request_bytes % 32 or self.memory_request_bytes > self.packet_payload_bytes:
            raise ValueError('Read descriptor must contain whole native words and fit the packet payload')
        if self.packet_payload_bytes < 32:
            raise ValueError('Packet payload must fit one native word')
        if (self.packet_payload_bytes + self.header_bytes + self.flit_bytes - 1) // self.flit_bytes > self.injection_flits:
            raise ValueError('NI must hold one complete packet including its header')


def mesh_system(rows=2, columns=2, **options):
    """Debug platform: one tile/engine/MC per reticle. Explicit synthetic wire recipe."""
    positive(rows, 'rows'); positive(columns, 'columns')
    period = options.get('noc_period_ps', 1000)
    width = options.get('flit_bytes', 16) * 8
    tiles = tuple(TileSpec(f'c{y * columns + x}', f'r{y * columns + x}', x, y)
                  for y in range(rows) for x in range(columns))
    memories = tuple(MemorySpec(f'm{i}', t.id) for i, t in enumerate(tiles))
    links = []
    for a in tiles:
        for b in tiles:
            if abs(a.x-b.x) + abs(a.y-b.y) == 1:
                key = f'{a.id}>{b.id}'
                # Illustrative 10 mm segment, two explicitly charged pipeline stages.
                links.append(PhysicalLink(key, a.id, b.id, 'stitch', key, width, period, 2, 2, 10000))
    for m in memories:
        for src, dst in ((m.home_tile, m.id), (m.id, m.home_tile)):
            key = f'{src}>{dst}'
            links.append(PhysicalLink(key, src, dst, 'HB', key, width, period, 1, 1, 20))
    return SystemSpec(tiles, memories, tuple(links), **options)
