"""Physical wire segments compose a router channel; stitching is only a boundary segment."""
from dataclasses import dataclass


@dataclass(frozen=True)
class WireSegment:
    kind: str
    start_um: tuple[int, int]
    end_um: tuple[int, int]
    pipeline_cycles: int

    @property
    def length_um(self): return sum(abs(a-b) for a, b in zip(self.start_um, self.end_um))


@dataclass(frozen=True)
class FabricChannel:
    id: str
    src: str
    dst: str
    segments: tuple[WireSegment, ...]
    data_bits: int = 1024
    control_bits: int = 1024
    period_ps: int = 1000
    channel_cycles: int = 61
    fine_hops: int = 64

    @property
    def length_um(self): return sum(s.length_um for s in self.segments)

    @property
    def resource_id(self): return self.id

    @property
    def width_bits(self): return self.data_bits

    @property
    def pipeline_cycles(self): return self.channel_cycles

    @property
    def credit_cycles(self): return self.channel_cycles

    @property
    def kind(self): return 'fabric_channel'


@dataclass(frozen=True)
class PhysicalResourceGraph:
    routers: tuple
    channels: tuple[FabricChannel, ...]

    def __post_init__(self):
        routers = {r.id: r for r in self.routers}
        if len(routers) != len(self.routers): raise ValueError('Duplicate router identity')
        ids, edges = set(), set()
        degrees = {r: 1 for r in routers}  # one shared local injection/ejection port
        for c in self.channels:
            if c.id in ids or (c.src, c.dst) in edges or c.src not in routers or c.dst not in routers:
                raise ValueError('Duplicate or invalid physical channel')
            if c.src == c.dst or not c.segments or c.channel_cycles < 1:
                raise ValueError('Physical channel must have a nonempty timed path')
            if c.segments[0].start_um != routers[c.src].position_um or c.segments[-1].end_um != routers[c.dst].position_um:
                raise ValueError('Channel endpoints do not match router positions')
            if any(a.end_um != b.start_um for a, b in zip(c.segments, c.segments[1:])):
                raise ValueError('Disconnected wire segments')
            for s in c.segments:
                if s.kind not in ('intra_reticle', 'boundary_stitch') or s.pipeline_cycles < 1:
                    raise ValueError('Unknown or untimed wire segment')
            ids.add(c.id); edges.add((c.src, c.dst)); degrees[c.src] += 1
        if any(degrees[k] > r.port_budget for k, r in routers.items()):
            raise ValueError('Physical router port budget exceeded')
        if any((b, a) not in edges for a, b in edges):
            raise ValueError('First executable fabric requires explicit reverse channels')
        reached = {next(iter(routers))}
        while True:
            nxt = reached | {b for a, b in edges if a in reached}
            if nxt == reached: break
            reached = nxt
        if reached != set(routers): raise ValueError('Disconnected compute fabric')

    def route(self, src, dst):
        from collections import deque
        queue = deque([(src, ())]); visited = {src}
        while queue:
            cur, path = queue.popleft()
            if cur == dst: return path
            for c in sorted(self.channels, key=lambda c: c.id):
                if c.src == cur and c.dst not in visited:
                    queue.append((c.dst, path+(c.id,))); visited.add(c.dst)
        raise ValueError(f'No physical fabric route from {src} to {dst}')
