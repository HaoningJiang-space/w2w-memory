"""Matched central/distributed vertical injection; external organization is separate."""
from math import ceil
from ..compute_fabric import ReticleRegion
from ..memory_wafer import DRAMDomain, MemoryBankGroup
from ..vertical_interface import VerticalPort, MemoryGateway, CollectionPath, ExternalPort
from ..wafer_stack import WaferStack
from .distributed_compute import distributed_compute


def vertical_memory(organization='distributed', *, rows=2, columns=2):
    if organization not in ('central','distributed','external'): raise ValueError('Unknown access organization')
    regions, clusters, routers, lateral = distributed_compute(rows,columns)
    memories, domains, ports, gateways, groups, collection, external = [],[],[],[],[],[],[]
    for n, region in enumerate(regions):
        memory = ReticleRegion(f'mr{n}',region.origin_um,region.size_um,'memory'); memories.append(memory)
        local = sorted((c for c in clusters if c.reticle_id==region.id),key=lambda c:(c.position_um[1],c.position_um[0]))
        center = tuple(o+s//2 for o,s in zip(region.origin_um,region.size_um))
        quadrant = [[] for _ in range(4)]
        for y in range(4):
            for x in range(8):
                pos=(region.origin_um[0]+(2*x+1)*region.size_um[0]//16,
                     region.origin_um[1]+(2*y+1)*region.size_um[1]//8)
                d=DRAMDomain(f'd{n}_{y*8+x}',memory.id,pos); domains.append(d)
                quadrant[(y//2)*2+x//4].append(d)
        if organization=='central':
            g=MemoryGateway(f'g{n}',region.id,center,local[0].router_id,128,128*1024,32,
                router_access_cycles=64)
            gateways.append(g)
        if organization=='external':
            # One declared edge I/O per physical region. Native service is an
            # off-wafer proxy; there is no HB and no uncharged local shortcut.
            edge=(regions[0].origin_um[0],region.origin_um[1]+region.size_um[1]//2)
            e=ExternalPort(f'io{n}',edge,local[0].router_id,32,128*1024,32); external.append(e)
        for k, subset in enumerate(quadrant):
            if organization=='distributed':
                g=MemoryGateway(f'g{n}_{k}',region.id,local[k].position_um,local[k].router_id,
                    32,32*1024,8); gateways.append(g)
            gateway = f'g{n}' if organization=='central' else f'g{n}_{k}' if organization=='distributed' else f'io{n}'
            groups.append(MemoryBankGroup(f'm{n}_{k}',tuple(d.id for d in subset),gateway,
                f'pool{n}' if organization in ('central','external') else f'pool{n}_{k}',
                32 if organization in ('central','external') else 8))
        if organization!='external':
            for g in [g for g in gateways if g.reticle_id==region.id]:
                subset=[d for d in domains if d.region_id==memory.id and
                    any(d.id in group.domain_ids and group.gateway_id==g.id for group in groups)]
                p=VerticalPort(f'hb_{g.id}',memory.id,g.position_um,tuple(d.id for d in subset),
                    g.id,len(subset)*128,hb_sites=len(subset)*128+64); ports.append(p)
                for d in subset:
                    length=sum(abs(a-b) for a,b in zip(d.position_um,p.position_um))
                    collection.append(CollectionPath(f'{d.id}>{p.id}',d.id,p.id,g.id,length,
                        pipeline_cycles=max(1,ceil(length/1000))))
    return WaferStack(f'v3-{organization}-{rows}x{columns}',regions,clusters,routers,
        tuple(memories),tuple(domains),lateral,tuple(ports),tuple(gateways),tuple(groups),
        tuple(collection),tuple(external))
