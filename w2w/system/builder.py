"""Validate explicit forwarding, dimensional routes and frozen residency before execution."""
from collections import defaultdict


class SystemBuilder:
    def __init__(self, spec):
        self.spec = spec
        self.tiles = {t.id: t for t in spec.tiles}
        self.memories = {m.id: m for m in spec.memories}
        self.links = {link.id: link for link in spec.links}
        if (len(self.tiles) != len(spec.tiles) or len(self.memories) != len(spec.memories)
                or set(self.tiles) & set(self.memories) or len(self.links) != len(spec.links)):
            raise ValueError('Duplicate physical node/link ID')
        if not self.tiles or not self.memories:
            raise ValueError('Compute and memory nodes must both exist')
        if len({(t.x, t.y) for t in spec.tiles}) != len(spec.tiles):
            raise ValueError('Duplicate tile coordinate')
        self.xy = {(t.x, t.y): t.id for t in spec.tiles}
        self.edges = {}
        resources = set()
        for memory in spec.memories:
            if memory.home_tile not in self.tiles:
                raise ValueError('Unknown home controller')
        for link in spec.links:
            if (link.src not in self.tiles and link.src not in self.memories
                    or link.dst not in self.tiles and link.dst not in self.memories):
                raise ValueError('Unknown link endpoint')
            if link.resource_id in resources or (link.src, link.dst) in self.edges:
                raise ValueError('A physical resource cannot be duplicated into independent capacities')
            resources.add(link.resource_id)
            self.edges[link.src, link.dst] = link.id
            if (link.kind != 'HB' and link.width_bits != spec.flit_bytes*8
                    or link.period_ps != spec.noc_period_ps):
                raise ValueError('First network requires one link clock/flit width; no implicit CDC/SerDes')
            if link.src in self.tiles and link.dst in self.tiles:
                a, b = self.tiles[link.src], self.tiles[link.dst]
                if abs(a.x-b.x) + abs(a.y-b.y) != 1:
                    raise ValueError('First network requires mesh-neighbor links')
                expected = 'intra_reticle' if a.reticle == b.reticle else 'stitch'
                if link.kind != expected or expected == 'stitch' and not spec.allow_stitching:
                    raise ValueError('Illegal cross-reticle connection in this platform')
            else:
                memory = self.memories.get(link.src) or self.memories.get(link.dst)
                tile = link.dst if link.src in self.memories else link.src
                if tile != memory.home_tile or link.kind != 'HB':
                    raise ValueError('Only explicit home HB is supported in B0/B1')

    def route(self, src, dst):
        """Memory nodes may terminate/inject packets, never transit other traffic."""
        if src == dst:
            if src not in self.tiles:
                raise ValueError('Local memory-to-memory communication is unsupported')
            return ()
        route = []
        end = self.memories[dst].home_tile if dst in self.memories else dst
        cur = src
        if cur in self.memories:
            nxt = self.memories[cur].home_tile
            route.append(self._edge(cur, nxt)); cur = nxt
        if cur not in self.tiles or end not in self.tiles:
            raise ValueError('Unknown routing endpoint')
        target = self.tiles[end]
        while cur != end:
            tile = self.tiles[cur]
            x, y = tile.x, tile.y
            if x != target.x: x += 1 if target.x > x else -1
            else: y += 1 if target.y > y else -1
            nxt = self.xy.get((x, y))
            route.append(self._edge(cur, nxt)); cur = nxt
        if dst in self.memories:
            route.append(self._edge(cur, dst))
        return tuple(route)

    def _edge(self, src, dst):
        try:
            return self.edges[src, dst]
        except KeyError as exc:
            raise ValueError(f'No executable route: missing {src} -> {dst}') from exc

    def validate_graph(self, graph):
        tasks = {t.id: t for t in graph.tasks}
        objects = {o.id: o for o in graph.objects}
        occupied = defaultdict(list)
        for obj in graph.objects:
            if obj.memory not in self.memories:
                raise ValueError('Unknown resident memory')
            stop = obj.offset_bytes + obj.size_bytes
            if stop > self.memories[obj.memory].capacity_bytes:
                raise ValueError('Object exceeds DRAM capacity')
            if any(obj.offset_bytes < b and a < stop for a, b in occupied[obj.memory]):
                raise ValueError('Resident objects overlap')
            occupied[obj.memory].append((obj.offset_bytes, stop))
        self.footprint = {}
        for task in graph.tasks:
            if task.tile not in self.tiles:
                raise ValueError('Unknown compute tile')
            size = task.scratch_bytes
            size += sum(e.size_bytes for e in graph.data if task.id in (e.producer, e.consumer))
            for read in task.reads:
                if read.object_id not in objects:
                    raise ValueError('Unknown read object')
                obj = objects[read.object_id]
                if read.offset_bytes + read.size_bytes > obj.size_bytes:
                    raise ValueError('Read outside resident object')
                mc = self.memories[obj.memory].home_tile
                if self.spec.baseline == 'B0' and mc != task.tile:
                    raise ValueError('B0 forbids remote memory; compute communication remains legal')
                for src, dst in ((task.tile, mc), (mc, obj.memory), (obj.memory, mc), (mc, task.tile)):
                    self.route(src, dst)
                size += read.size_bytes
            if size > self.tiles[task.tile].sram_bytes:
                raise ValueError(f'Task {task.id} working set exceeds SRAM; provide an explicitly tiled graph')
            self.footprint[task.id] = size
        for edge in graph.data:
            self.route(tasks[edge.producer].tile, tasks[edge.consumer].tile)
        return self

    def physical_record(self):
        return dict(reticle_count=len({t.reticle for t in self.spec.tiles}),
                    tile_count=len(self.tiles), compute_engine_count=len(self.tiles),
                    memory_count=len(self.memories),
                    tiles_per_reticle={r: sum(t.reticle == r for t in self.spec.tiles)
                                       for r in sorted({t.reticle for t in self.spec.tiles})},
                    lane_bits=sum(l.width_bits for l in self.spec.links),
                    wire_bit_um=sum(l.width_bits*l.length_um for l in self.spec.links),
                    pipeline_bits=sum(l.width_bits*l.pipeline_cycles for l in self.spec.links),
                    area_um2=None, calibration='synthetic explicit segments; no physical timing signoff')
