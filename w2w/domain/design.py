"""Frozen design values; geometry algorithms and solvers live outside domain."""
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from math import isclose, isfinite
from struct import pack
from .endpoint import EndpointSpec


@dataclass(frozen=True)
class Geometry:
    name: str
    compute_xy: tuple
    memory_xy: tuple
    # (compute, memory, compute_port, memory_port, compute_fraction, memory_fraction)
    routes: tuple
    bank_xy: tuple
    port_xy: tuple

    def __post_init__(self):
        for key in ('compute_xy', 'memory_xy', 'routes', 'bank_xy', 'port_xy'):
            object.__setattr__(self, key, tuple(tuple(row) for row in getattr(self, key)))
        if not self.compute_xy or not self.memory_xy or not self.bank_xy or not self.port_xy:
            raise ValueError('Geometry must contain nodes, banks and ports')
        for c, m, cp, mp, cf, mf in self.routes:
            if (not 0 <= c < len(self.compute_xy) or not 0 <= m < len(self.memory_xy)
                    or not 0 <= cp < len(self.port_xy) or not 0 <= mp < len(self.port_xy)
                    or not 0 < cf <= 1 + 1e-12 or not 0 < mf <= 1 + 1e-12):
                raise ValueError('Invalid physical route')


@dataclass(frozen=True)
class Exposure:
    mask: tuple
    port_bits: tuple
    clock_ghz: float = 1.
    controller_tb_s: float = 4.
    bank_bw: float = 1 / 32
    bank_capacity_gib: float = .5
    object_gib: float = 4.
    pipeline_spacing_mm: float = 2.

    def __post_init__(self):
        object.__setattr__(self, 'mask', tuple(tuple(ps) for ps in self.mask))
        object.__setattr__(self, 'port_bits', tuple(self.port_bits))
        if (not self.mask or any(not ps or len(set(ps)) != len(ps)
                                or any(not 0 <= p < len(self.port_bits) or self.port_bits[p] <= 0 for p in ps)
                                for ps in self.mask)):
            raise ValueError('Invalid exposure or unconfigured port')
        if any(not isinstance(w, int) or w < 0 for w in self.port_bits):
            raise ValueError('Port widths must be nonnegative integers')
        if not all(isfinite(v) and v > 0 for v in (self.clock_ghz, self.controller_tb_s,
                   self.bank_bw, self.bank_capacity_gib, self.object_gib, self.pipeline_spacing_mm)):
            raise ValueError('Invalid physical capacity')


@dataclass(frozen=True)
class StaticLayout:
    shares: tuple

    def __post_init__(self):
        values = tuple(tuple(float(v) for v in row) for row in self.shares)
        if (not values or not values[0] or any(len(row) != len(values[0]) for row in values)
                or any(not isfinite(v) or v < 0 for row in values for v in row)
                or any(not isclose(sum(row), 1., abs_tol=1e-10) for row in values)):
            raise ValueError('Static layout requires nonnegative unit byte fractions')
        object.__setattr__(self, 'shares', values)

    @property
    def sha256(self):
        return sha256(b''.join(pack('<d', v) for row in self.shares for v in row)).hexdigest()


@dataclass(frozen=True)
class MemoryFabricDesign:
    name: str
    structure: str
    geometry: Geometry
    exposure: Exposure
    endpoint: EndpointSpec
    layout: StaticLayout
    home_fraction: Fraction = Fraction(1, 2)
    # One immutable physical shared port per memory, independent of active set.
    shared_directions: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, 'home_fraction', Fraction(self.home_fraction))
        object.__setattr__(self, 'shared_directions', tuple(self.shared_directions))
        if not 0 < self.home_fraction <= 1:
            raise ValueError('Invalid frozen home fraction')
        nb = len(self.exposure.mask)
        if (nb != len(self.geometry.bank_xy) or len(self.endpoint.widths) != len(self.exposure.port_bits)
                or len(self.geometry.port_xy) != len(self.exposure.port_bits)
                or len(self.layout.shares) != len(self.geometry.compute_xy)
                or len(self.layout.shares[0]) != len(self.geometry.memory_xy) * nb):
            raise ValueError('Design dimensions disagree')
        if any(self.endpoint.widths[p] == 0 for ps in self.exposure.mask for p in ps):
            raise ValueError('Exposure names an unconfigured endpoint')
        for bank in range(len(self.layout.shares[0])):
            stored = sum(row[bank] for row in self.layout.shares) * self.exposure.object_gib
            if stored > self.exposure.bank_capacity_gib + 1e-9:
                raise ValueError('Static storage capacity exceeded')
        group = self.endpoint.shared_fifo_ports
        if not group:
            if self.shared_directions:
                raise ValueError('Direction configuration requires a static shared FIFO')
            return
        if (len(self.shared_directions) != len(self.geometry.memory_xy)
                or any(p not in group for p in self.shared_directions)
                or any(not set(group).issubset(ps) for ps in self.exposure.mask)):
            raise ValueError('Shared FIFO requires a frozen direction for every memory and full template support')
        routes = {}
        for c, m, _, p, _, _ in self.geometry.routes:
            routes.setdefault((c, m), set()).add(p)
        for c, shares in enumerate(self.layout.shares):
            for bank, fraction in enumerate(shares):
                if fraction == 0:
                    continue
                m, b = divmod(bank, nb)
                ports = routes.get((c, m), set()) & set(self.exposure.mask[b])
                if len(ports) != 1:
                    raise ValueError('Static shared FIFO requires a unique physical route for every byte')
                p = next(iter(ports))
                if p in group and p != self.shared_directions[m]:
                    raise ValueError('Frozen layout uses an unselected shared direction')
