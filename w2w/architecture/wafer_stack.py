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
    resource_budget: object = None

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
        for layer_regions in (self.compute_reticles,self.memory_regions):
            for i,a in enumerate(layer_regions):
                for b in layer_regions[i+1:]:
                    if all(a.origin_um[k]<b.origin_um[k]+b.size_um[k] and b.origin_um[k]<a.origin_um[k]+a.size_um[k] for k in (0,1)):
                        raise ValueError('Physical regions overlap on the same wafer')
        if any(d.capacity_bytes not in (16*1024**2,64*1024**2) or d.data_bits!=128 or d.period_ps!=3760
               or d.command_read_entries!=self.native_policy.read_entries or d.return_atoms<1 for d in self.dram_domains):
            raise ValueError('Native physical budgets do not match the declared service')
        for layer, items in (('compute', (*self.compute_clusters, *self.routers, *self.gateways)),
                             ('memory', self.dram_domains)):
            for obj in items:
                region = regions.get(getattr(obj, 'reticle_id', getattr(obj, 'region_id', None)))
                if region is None or region.layer != layer or not region.contains(obj.position_um):
                    raise ValueError('Resource lies outside its physical region')
        for c in self.compute_clusters:
            if c.router_id not in routers: raise ValueError('Unknown cluster router')
            if c.position_um!=routers[c.router_id].position_um:
                raise ValueError('First compiler requires co-located cluster/router or an explicit attachment path')
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
            if p.position_um!=gateways[p.gateway_id].position_um:
                raise ValueError('Vertical HB landing is not aligned with its logic gateway')
        for group in self.bank_groups:
            if not group.domain_ids or len(set(group.domain_ids))!=len(group.domain_ids) or any(d not in domains for d in group.domain_ids):
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
            if p.domain_id not in ports[p.port_id].domain_ids or p.period_ps!=domains[p.domain_id].period_ps:
                raise ValueError('Collection path is not attached to the declared native port')
            expected = sum(abs(a-b) for a, b in zip(domains[p.domain_id].position_um, ports[p.port_id].position_um))
            if p.length_um != expected or p.pipeline_cycles < 1:
                raise ValueError('Collection transport must use physical coordinates and pay delay')
        pools={}
        for group in self.bank_groups:
            prior=pools.setdefault(group.mc_pool_id,(group.gateway_id,group.mc_slots))
            if prior!=(group.gateway_id,group.mc_slots) or gateways.get(group.gateway_id,external.get(group.gateway_id)).descriptor_slots!=group.mc_slots:
                raise ValueError('Descriptor pool has inconsistent physical ownership')
        expected={(d,g.gateway_id) for g in self.bank_groups for d in g.domain_ids if g.gateway_id in gateways}
        if {(p.domain_id,p.gateway_id) for p in self.collection_paths}!=expected:
            raise ValueError('Missing physical native-to-gateway collection path')
        PhysicalResourceGraph(self.routers, self.lateral_links)
        from .resources import ResourceBudget
        if self.resource_budget is None:
            object.__setattr__(self,'resource_budget',ResourceBudget.from_stack(self))
        self.resource_budget.validate(self)

    @property
    def physical_graph(self): return PhysicalResourceGraph(self.routers, self.lateral_links)
