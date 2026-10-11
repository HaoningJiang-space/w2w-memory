"""Non-executable domain-aligned proposal; never masquerades as a V3 preset."""
from dataclasses import dataclass, asdict
from .vertical_interface import VerticalPort


@dataclass(frozen=True)
class DomainLogicTile:
    id: str
    domain_id: str
    neighborhood_id: str
    reticle_id: str
    position_um: tuple
    pe_count: int
    macs_per_cycle: int
    sram_bytes: int
    cache_bytes: int
    hb_data_bits: int
    hb_control_bits: int
    staging_bytes: int
    outstanding_descriptors: int
    mc_slots: int
    direct_fifo_bytes: int = 64
    association_bytes: int = 32


@dataclass(frozen=True)
class DomainComputeSpecification:
    baseline_name: str
    tiles: tuple[DomainLogicTile, ...]
    neighborhoods: tuple
    hb_sites: int
    landing_footprint_um2: int
    native_period_ps: int
    baseline_gateway_bytes_per_ns: int
    removed_collection_wire_bit_um: int
    local_star_one_way_wire_bit_um: int
    collective_fetch_contexts: int = 2
    schema: str = 'w2w.domain-compute-proposal.v1'
    executable: bool = False

    def compile(self):
        raise ValueError('Proposal only: local fabric timing, state association, FIFO/cache protocol and matched-resolution baseline are not executable')

    def record(self):
        r=asdict(self)
        r['resources']={k:sum(getattr(t,k) for t in self.tiles) for k in
            ('pe_count','macs_per_cycle','sram_bytes','cache_bytes','hb_data_bits','hb_control_bits',
             'staging_bytes','outstanding_descriptors','mc_slots','direct_fifo_bytes','association_bytes')}
        r['limits']=[
            '512-PE tiles are still aggregate models; changing resolution is not hardware novelty',
            'shared two matrix issue contexts per eight-domain neighborhood; association/FIFO state charged separately',
            'data/control pad sites conserve the baseline; 4-bit forward/reverse control per domain needs serialization',
            'staging repartition conserves bytes/MC slots, not the timing contract or descriptor coverage',
            'new bidirectional local branches cost at least twice the one-way wire proxy; not free activation broadcast',
            'HB landing geometry checked; compute/SRAM macro footprints, clocks, power and area are uncalibrated',
            'global fabric unchanged conceptually; 128 direct endpoints cannot silently reuse the V3 co-located-router compiler']
        return r


def domain_compute_specification(stack, *, cache_bytes_per_cluster=184*1024**2):
    if type(cache_bytes_per_cluster) is not int or cache_bytes_per_cluster<1:
        raise ValueError('The retained-cache proposal requires a positive integer data budget')
    if len(stack.compute_clusters)!=len(stack.bank_groups) or len(stack.gateways)!=len(stack.bank_groups):
        raise ValueError('This proposal requires the distributed one-cluster/eight-domain neighborhood reference')
    gateways={g.id:g for g in stack.gateways};domains={d.id:d for d in stack.dram_domains}
    ports={p.gateway_id:p for p in stack.vertical_ports};regions={r.id:r for r in stack.compute_reticles}
    seen=set();tiles=[];neighborhoods=[];footprints=[];sites=0;star=0
    for group in stack.bank_groups:
        n=len(group.domain_ids);g=gateways[group.gateway_id];p=ports[g.id]
        clusters=[c for c in stack.compute_clusters if c.router_id==g.router_id and c.position_um==g.position_um]
        if n!=8 or len(clusters)!=1 or seen.intersection(group.domain_ids):
            raise ValueError('Disjoint eight-domain neighborhoods and exact cluster/gateway co-location required')
        c=clusters[0];seen.update(group.domain_ids)
        if c.profile.period_ps!=1000:raise ValueError('This fixed proposal uses the recorded 1 ns logic clock')
        budgets=(c.profile.pe_count,c.profile.macs_per_cycle,c.profile.sram_bytes,cache_bytes_per_cluster,
                 p.data_bits,p.control_bits,g.staging_bytes,32,g.descriptor_slots)
        if any(v%n for v in budgets) or cache_bytes_per_cluster>=c.profile.sram_bytes:
            raise ValueError('No resource rounding, bandwidth or cache duplication permitted')
        divided=tuple(v//n for v in budgets)
        if divided[4]!=128 or divided[5]%2 or divided[5]<2:
            raise ValueError('One native RWDL and finite bidirectional control lanes per landing required')
        neighborhood=[]
        for name in group.domain_ids:
            d=domains[name];neighborhood.append('pe_'+name)
            tile=DomainLogicTile('pe_'+name,name,g.id,c.reticle_id,d.position_um,*divided)
            if tile.direct_fifo_bytes+tile.association_bytes>tile.sram_bytes-tile.cache_bytes:
                raise ValueError('FIFO/association must fit inside original non-cache SRAM')
            tiles.append(tile)
            landing=VerticalPort('landing_'+name,d.region_id,d.position_um,(name,),g.id,128,
                period_ps=d.period_ps,control_bits=tile.hb_control_bits,hb_sites=128+tile.hb_control_bits,
                landing_pitch_um=p.landing_pitch_um)
            bounds=landing.landing_bounds_um;sites+=landing.hb_sites
            region=regions[c.reticle_id]
            if not all(region.contains(q) for q in ((bounds[0],bounds[1]),(bounds[2],bounds[3]))):
                raise ValueError('Landing exceeds aligned reticle')
            footprints.append(bounds)
            star+=128*sum(abs(a-b) for a,b in zip(d.position_um,g.position_um))
        neighborhoods.append(dict(id=g.id,tiles=tuple(neighborhood),global_router=g.router_id,
            root_position_um=g.position_um,collective_issue_metadata_bytes=136))
    for i,(x,y,a,b) in enumerate(footprints):
        if any(x<d and u<a and y<e and v<b for u,v,d,e in footprints[i+1:]):
            raise ValueError('Domain landings overlap')
    if seen!=set(domains) or sites!=sum(p.hb_sites for p in stack.vertical_ports):
        raise ValueError('Native domains or HB signal site budget changed')
    if len({d.period_ps for d in domains.values()})!=1:
        raise ValueError('Declare a separate mixed-clock specification')
    return DomainComputeSpecification(stack.name,tuple(tiles),tuple(neighborhoods),sites,
        sum((a-x)*(b-y) for x,y,a,b in footprints),next(iter(domains.values())).period_ps,
        sum(g.data_bytes_per_cycle for g in stack.gateways),
        sum(p.data_bits*p.length_um for p in stack.collection_paths),star)
