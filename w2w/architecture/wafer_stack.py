"""Validated, immutable physical machine identity."""
from dataclasses import dataclass
from .physical_graph import PhysicalResourceGraph
from .memory_wafer import NativePolicy


@dataclass(frozen=True)
class WaferStack:
    name: str
    compute_reticles: tuple
    compute_clusters: tuple
    routers: tuple
    memory_regions: tuple
    dram_domains: tuple
    lateral_links: tuple
    vertical_ports: tuple
    gateways: tuple
    bank_groups: tuple
    collection_paths: tuple
    external_ports: tuple = ()
    native_policy: NativePolicy = NativePolicy()
    wafer_diameter_um: int = 300000
    schema: str = 'w2w.wafer-stack.v3'

    def __post_init__(self):
        for name in ('compute_reticles', 'compute_clusters', 'routers', 'memory_regions',
                     'dram_domains', 'lateral_links', 'vertical_ports', 'gateways',
                     'bank_groups', 'collection_paths', 'external_ports'):
            object.__setattr__(self, name, tuple(getattr(self, name)))
            items = getattr(self, name)
            if len({x.id for x in items}) != len(items): raise ValueError(f'Duplicate {name} identity')
        regions = {r.id: r for r in (*self.compute_reticles, *self.memory_regions)}
        routers = {r.id: r for r in self.routers}
        domains = {d.id: d for d in self.dram_domains}
        gateways = {g.id: g for g in self.gateways}
        ports = {p.id: p for p in self.vertical_ports}
        external = {p.id: p for p in self.external_ports}
        for layer, items in (('compute', (*self.compute_clusters, *self.routers, *self.gateways)),
                             ('memory', self.dram_domains)):
            for obj in items:
                region = regions.get(getattr(obj, 'reticle_id', getattr(obj, 'region_id', None)))
                if region is None or region.layer != layer or not region.contains(obj.position_um):
                    raise ValueError('Resource lies outside its physical region')
        for c in self.compute_clusters:
            if c.router_id not in routers: raise ValueError('Unknown cluster router')
        for r in self.compute_reticles:
            x, y = r.origin_um; w, h = r.size_um
            if any(a*a+b*b > (self.wafer_diameter_um//2)**2 for a in (x, x+w) for b in (y, y+h)):
                raise ValueError('Reticle outside wafer boundary')
        for p in self.vertical_ports:
            if p.gateway_id not in gateways or not p.domain_ids or p.data_bits < 128 or p.data_bits%128:
                raise ValueError('Invalid vertical port')
            if any(d not in domains or domains[d].region_id != p.region_id for d in p.domain_ids):
                raise ValueError('Vertical port refers to another memory region')
            if not regions[p.region_id].contains(p.position_um) or p.hb_sites < p.data_bits+p.control_bits:
                raise ValueError('HB landing or site budget invalid')
        for group in self.bank_groups:
            if not group.domain_ids or any(d not in domains for d in group.domain_ids):
                raise ValueError('Unknown native domain in memory view')
            if group.gateway_id not in gateways and group.gateway_id not in external:
                raise ValueError('Unknown memory gateway')
            for d in group.domain_ids:
                if group.gateway_id in gateways and not any(d in p.domain_ids and p.gateway_id == group.gateway_id for p in self.vertical_ports):
                    raise ValueError('No vertical path for memory view')
        for g in (*self.gateways, *self.external_ports):
            if g.router_id not in routers or g.data_bytes_per_cycle < 16 or g.data_bytes_per_cycle%16:
                raise ValueError('Unknown gateway router or unsupported beat width')
            if g.staging_bytes < g.descriptor_slots*4096 or g.descriptor_slots < 1:
                raise ValueError('Gateway must reserve finite descriptor return storage')
        for p in self.collection_paths:
            if p.domain_id not in domains or p.port_id not in ports or p.gateway_id != ports[p.port_id].gateway_id:
                raise ValueError('Invalid native collection path')
            expected = sum(abs(a-b) for a, b in zip(domains[p.domain_id].position_um, ports[p.port_id].position_um))
            if p.length_um != expected or p.pipeline_cycles < 1:
                raise ValueError('Collection transport must use physical coordinates and pay delay')
        PhysicalResourceGraph(self.routers, self.lateral_links)

    @property
    def physical_graph(self): return PhysicalResourceGraph(self.routers, self.lateral_links)
