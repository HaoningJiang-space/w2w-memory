"""Validate explicit forwarding, dimensional routes and frozen residency before execution."""
from collections import defaultdict


class SystemBuilder:
    def __init__(self, spec):
        self.spec = spec
        self.tiles = {t.id: t for t in spec.tiles}
        self.memories = {m.id: m for m in spec.memories}
        self.links = {link.id: link for link in spec.links}
        if not hasattr(spec,'stack'):
            raise ValueError('Use a compiled physical Architecture V3 machine; V2 generators are frozen')
        self.v3 = True
        self.routers = {r.id:r for r in spec.routers}
        self.edges = {(l.src,l.dst):l.id for l in spec.links}
        if len(self.tiles)!=len(spec.tiles) or len(self.memories)!=len(spec.memories):
            raise ValueError('Duplicate execution endpoint')
        self.physical_graph = spec.stack.physical_graph

    def route(self,src,dst):
        return self.physical_graph.route(self.spec.endpoint_router(src),self.spec.endpoint_router(dst))

    def validate_graph(self, graph):
        tasks = {t.id: t for t in graph.tasks}
        objects = {o.id: o for o in graph.objects}
        occupied = defaultdict(list)
        physical_occupied=defaultdict(list);storage_signatures={}
        domains={d.id:d for d in self.spec.stack.dram_domains}
        for obj in graph.objects:
            if obj.memory not in self.memories:
                raise ValueError('Unknown resident memory')
            stop = obj.offset_bytes + obj.size_bytes
            if stop > self.memories[obj.memory].capacity_bytes:
                raise ValueError('Object exceeds DRAM capacity')
            if any(obj.offset_bytes < b and a < stop for a, b in occupied[obj.memory]):
                raise ValueError('Resident objects overlap')
            occupied[obj.memory].append((obj.offset_bytes, stop))
            memory=self.memories[obj.memory]
            storage=obj.storage_id or obj.id
            signature=(memory.domain_ids,obj.offset_bytes,obj.size_bytes)
            if storage in storage_signatures and storage_signatures[storage]!=signature:
                raise ValueError('Storage alias changes the physical content mapping')
            storage_signatures[storage]=signature
            start_word=obj.offset_bytes//32;stop_word=stop//32
            for bank,domain in enumerate(memory.domain_ids):
                first=start_word+(bank-start_word%memory.banks)%memory.banks
                count=max(0,(stop_word-first+memory.banks-1)//memory.banks)
                if not count:continue
                a,b=2*(first//memory.banks),2*(first//memory.banks+count)
                if b>domains[domain].capacity_bytes//16:raise ValueError('Storage exceeds a physical DRAM domain')
                for x,y,prior in physical_occupied[domain]:
                    if a<y and x<b and storage!=prior:
                        raise ValueError('Distinct resident content overlaps through native-domain aliases')
                physical_occupied[domain].append((a,b,storage))
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
        from w2w.architecture.resources import inventory
        return inventory(self.spec.stack)
