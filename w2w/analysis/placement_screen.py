"""Necessary resource work and route proxies, never a makespan predictor."""
from collections import Counter
from math import ceil
from w2w.system.builder import SystemBuilder


def screen(machine,graph,metadata):
    builder=SystemBuilder(machine).validate_graph(graph)
    objects={o.id:o for o in graph.objects};groups={g.id:g for g in machine.stack.bank_groups}
    domain_bytes=Counter();gateway_bytes=Counter();rx=Counter();inject=Counter();cuts=Counter()
    routers={r.id:r for r in machine.routers};byte_hops=0;remote_weights=0
    def transfer(src,dst,payload):
        nonlocal byte_hops
        if machine.endpoint_router(src)==machine.endpoint_router(dst):return
        count=ceil((payload+machine.header_bytes)/machine.flit_bytes)
        a,b=machine.endpoint_router(src),machine.endpoint_router(dst)
        inject[a]+=count
        byte_hops+=count*machine.flit_bytes*len(builder.route(src,dst))
        for axis in (0,1):
            if (routers[a].position_um[axis]<0)!=(routers[b].position_um[axis]<0):cuts[axis]+=count
    for task in graph.tasks:
        for access in task.reads:
            obj=objects[access.object_id];memory=builder.memories[obj.memory];group=groups[obj.memory]
            gateway_bytes[group.gateway_id]+=access.size_bytes;rx[task.tile]+=access.size_bytes
            begin=(obj.offset_bytes+access.offset_bytes)//32;words=access.size_bytes//32
            for bank,domain in enumerate(group.domain_ids):
                first=(bank-begin)%len(group.domain_ids)
                n=0 if first>=words else 1+(words-1-first)//len(group.domain_ids)
                domain_bytes[domain]+=n*32
            for offset in range(0,access.size_bytes,machine.memory_request_bytes):
                size=min(machine.memory_request_bytes,access.size_bytes-offset)
                transfer(task.tile,memory.home_tile,0);transfer(memory.home_tile,task.tile,size)
            if machine.endpoint_router(task.tile)!=machine.endpoint_router(memory.home_tile):remote_weights+=access.size_bytes
    for edge in graph.data:
        src=builder.tasks[edge.producer].tile if hasattr(builder,'tasks') else next(t.tile for t in graph.tasks if t.id==edge.producer)
        dst=next(t.tile for t in graph.tasks if t.id==edge.consumer)
        rx[dst]+=edge.size_bytes
        for offset in range(0,edge.size_bytes,machine.packet_payload_bytes):transfer(src,dst,min(machine.packet_payload_bytes,edge.size_bytes-offset))
    domains={d.id:d for d in machine.stack.dram_domains};gateways={g.id:g for g in machine.stack.gateways}
    macs=Counter();vectors=Counter();weight_reads=Counter()
    for task in graph.tasks:
        work=metadata['task_work'][task.id];macs[task.tile]+=work['macs'];vectors[task.tile]+=work['vector_ops']
        weight_reads[task.tile]+=sum(r.size_bytes for r in task.reads)
    profiles={c.id:c.profile for c in machine.stack.compute_clusters}
    cut_bounds={}
    for axis,name in enumerate(('x-midline','y-midline')):
        links=[l for l in machine.links if (routers[l.src].position_um[axis]<0)!=(routers[l.dst].position_um[axis]<0)]
        cut_bounds[name]=ceil(cuts[axis]*machine.noc_period_ps/len(links)) if links else 0
    bounds=dict(native_interface=max((ceil(v*domains[k].period_ps/(domains[k].data_bits//8)) for k,v in domain_bytes.items()),default=0),
        gateway_payload=max((ceil(v*machine.noc_period_ps/gateways[k].data_bytes_per_cycle) for k,v in gateway_bytes.items()),default=0),
        receiver_payload=max((ceil(v*machine.noc_period_ps/machine.rx_write_bytes_per_cycle) for v in rx.values()),default=0),
        fabric_injection=max(inject.values(),default=0)*machine.noc_period_ps,
        fabric_cut=max(cut_bounds.values(),default=0),
        compute_arithmetic=max((ceil(macs[k]/p.macs_per_cycle)*machine.noc_period_ps for k,p in profiles.items()),default=0),
        compute_vectors=max((ceil(vectors[k]/p.vector_ops_per_cycle)*machine.noc_period_ps for k,p in profiles.items()),default=0),
        compute_weight_read=max((ceil(weight_reads[k]/p.weight_read_bytes_per_cycle)*machine.noc_period_ps for k,p in profiles.items()),default=0))
    capacity=Counter()
    for obj in graph.objects:capacity[obj.memory]=max(capacity[obj.memory],obj.offset_bytes+obj.size_bytes)
    return dict(necessary_bounds_ps=bounds,max_necessary_bound_ps=max(bounds.values()),gateway_bytes=dict(gateway_bytes),
        domain_bytes=dict(domain_bytes),gateway_max_to_mean=max(gateway_bytes.values())/(sum(gateway_bytes.values())/len(gateways)),
        domain_max_to_mean=max(domain_bytes.values())/(sum(domain_bytes.values())/len(domains)),
        remote_weight_payload_bytes=remote_weights,reference_route_data_lane_byte_hops=byte_hops,cut_bounds_ps=cut_bounds,
        full_catalog_extent_bytes=dict(capacity),
        contract='cold compulsory reads; necessary interface/service/cut work, excludes command inefficiency and feedback; max is a lower bound, not predicted completion; reference-route byte-hops are a routing proxy, actual adaptive hops require execution')
