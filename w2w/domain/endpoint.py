"""Endpoint implementation and service envelope values, independent of scipy."""
from dataclasses import asdict, dataclass
from math import isfinite


@dataclass(frozen=True)
class NativeProfile:
    name: str = 'always_ready'
    ready: tuple = (1,)

    def __post_init__(self):
        object.__setattr__(self, 'ready', tuple(self.ready))
        if not self.ready or any(v not in (0, 1) for v in self.ready):
            raise ValueError('Native readiness must be a nonempty binary period')


@dataclass(frozen=True)
class EndpointSpec:
    widths: tuple
    depths: tuple
    word_bits: int = 256
    mode: str = 'buffered'
    serializer_location: str = 'bank'
    native: NativeProfile = NativeProfile()
    # One bank-local FIFO, statically attached to one of these physical ports.
    shared_fifo_ports: tuple = ()
    shared_serializer: bool = False

    def __post_init__(self):
        object.__setattr__(self, 'widths', tuple(self.widths))
        object.__setattr__(self, 'depths', tuple(self.depths))
        object.__setattr__(self, 'shared_fifo_ports', tuple(self.shared_fifo_ports))
        if (not self.widths or len(self.widths) != len(self.depths)
                or not isinstance(self.word_bits, int) or self.word_bits <= 0
                or self.mode not in ('buffered', 'direct')
                or self.serializer_location not in ('bank', 'port')):
            raise ValueError('Invalid implementation')
        for w, d in zip(self.widths, self.depths):
            if (not isinstance(w, int) or not 0 <= w <= self.word_bits
                    or not isinstance(d, int) or d < 0 or (w == 0 and d != 0)
                    or (self.mode == 'buffered' and w > 0 and d == 0)
                    or (self.mode == 'direct' and d != 0)):
                raise ValueError('Invalid width/depth or unconfigured output storage')
        group = self.shared_fifo_ports
        if not isinstance(self.shared_serializer, bool) or (self.shared_serializer and not group):
            raise ValueError('A shared serializer requires a static shared FIFO')
        if group and (self.mode != 'buffered' or self.serializer_location != 'bank'
                      or len(group) < 2 or len(set(group)) != len(group)
                      or any(not isinstance(p, int) or not 0 < p < len(self.widths) for p in group)
                      or any(self.widths[p] <= 0 for p in group)
                      or len({(self.widths[p], self.depths[p]) for p in group}) != 1):
            raise ValueError('Static shared FIFO requires equal bank-side buffered shared ports')

    def record(self):
        return asdict(self)


@dataclass(frozen=True)
class LinearLimit:
    label: tuple
    # Terms are ((client, global_bank, physical_edge), coefficient).
    terms: tuple
    capacity: float

    def __post_init__(self):
        object.__setattr__(self, 'label', tuple(self.label))
        object.__setattr__(self, 'terms', tuple((tuple(key), float(v)) for key, v in self.terms))
        if (not isfinite(self.capacity) or self.capacity < 0
                or any(not isfinite(v) or v < 0 for _, v in self.terms)):
            raise ValueError('Invalid resource limit')


@dataclass(frozen=True)
class EndpointEnvelope:
    resource_caps: tuple = ()
    path_caps: tuple = ()
    limits: tuple = ()
    restrict_paths: bool = False
    scope: str = 'fluid upper envelope'

    def __post_init__(self):
        for name in ('resource_caps', 'path_caps'):
            values = tuple((tuple(key), float(v)) for key, v in getattr(self, name))
            if any(not isfinite(v) or v < 0 for _, v in values) or len({key for key, _ in values}) != len(values):
                raise ValueError('Invalid or duplicate capacity')
            object.__setattr__(self, name, values)
        object.__setattr__(self, 'limits', tuple(self.limits))

    def with_delivered_caps(self, caps):
        return EndpointEnvelope(self.resource_caps, tuple(sorted(caps.items())), self.limits,
                                True, 'scenario-specific achieved periodic reservation')
