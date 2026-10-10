"""Executed resource observations; no inferred additive stall decomposition."""
from collections import Counter
from fractions import Fraction
from math import ceil
from w2w.architecture.serialization import from_record


def summarize_pressure(result):
    stack=from_record(result['spec']['stack']);native=result['native'];network=result['network']
    duration=result['makespan_ps'];routers={r.id:r for r in stack.routers}
    links={c.id:c for c in stack.lateral_links};flits=network['link_flits']
    if set(flits)-set(links):raise ValueError('Executed traffic uses an unknown physical channel')
    traffic=Counter();byte_um=0
    for key,count in flits.items():
        link=links[key];a,b=routers[link.src],routers[link.dst]
        traffic['intra_reticle' if a.reticle_id==b.reticle_id else 'cross_reticle']+=count
        byte_um+=count*result['spec']['flit_bytes']*link.length_um
    cuts={}
    for region in stack.compute_reticles:
        for axis,label in enumerate(('x','y')):
            mid=region.origin_um[axis]+Fraction(region.size_um[axis],2)
            for direction,positive in (('positive',True),('negative',False)):
                selected=[]
                for link in stack.lateral_links:
                    a,b=routers[link.src],routers[link.dst]
                    if a.reticle_id!=region.id or b.reticle_id!=region.id:continue
                    lo,hi=a.position_um[axis],b.position_um[axis]
                    if (lo<mid<=hi if positive else hi<mid<=lo):selected.append(link)
                capacity=sum((Fraction(c.data_bits,8*c.period_ps) for c in selected),Fraction(0))
                cells=sum(flits.get(c.id,0) for c in selected)
                wire_bytes=cells*result['spec']['flit_bytes']
                cuts[f'{region.id}/{label}/{direction}']=dict(channels=[c.id for c in selected],
                    flits=cells,data_lane_bytes=wire_bytes,
                    necessary_service_ps=ceil(Fraction(wire_bytes)/capacity) if capacity else 0,
                    average_lane_service_fraction=float(Fraction(wire_bytes)/capacity/duration) if capacity else 0)
    controllers=native['stats']['controller'];domains=stack.dram_domains
    if len(controllers)!=len(domains):raise ValueError('Native statistics do not cover the physical domains')
    names=('num_read_reqs','read_row_hits','read_row_misses','read_row_conflicts','read_latency','num_maintenance_reqs_served')
    native_totals=Counter();domain_stats={}
    for index,(domain,stats) in enumerate(zip(domains,controllers)):
        row={key:stats[key] for key in names}
        atoms=native['channel_atoms'].get(str(index),0)
        if (row['num_read_reqs']!=atoms or
                sum(row[k] for k in ('read_row_hits','read_row_misses','read_row_conflicts'))!=atoms):
            raise ValueError('Native row classification or physical-domain atom accounting differs')
        native_totals.update(row)
        domain_stats[domain.id]=dict(row,atoms=atoms,
            read_bus_service_fraction=atoms*domain.period_ps/duration,
            average_controller_read_latency_ps=row['read_latency']*domain.period_ps/atoms if atoms else 0)
    if native_totals['num_read_reqs']!=native['completed_atoms']:
        raise ValueError('Controller statistics disagree with completed native atoms')
    native_totals=dict(native_totals)
    reads=native_totals['num_read_reqs']
    native_totals['average_controller_read_latency_ps']=native_totals['read_latency']*native['tck_ps']/reads if reads else 0
    gateway_stats={}
    for gateway in stack.gateways:
        busy=native['gateway_busy_cycles'].get(gateway.id,0)
        payload=native['gateway_bytes'].get(gateway.id,0)
        gateway_stats[gateway.id]=dict(payload_bytes=payload,busy_cycles=busy,
            busy_cycle_fraction=busy*result['spec']['noc_period_ps']/duration,
            payload_lane_service_fraction=payload*result['spec']['noc_period_ps']/gateway.data_bytes_per_cycle/duration,
            queue_peak_bytes=native['gateway_queue_peak_bytes'].get(gateway.id,0))
    busiest=max(flits,key=flits.get,default=None)
    return dict(native_totals=native_totals,domains=domain_stats,gateways=gateway_stats,
        actual_hop_flits_by_scope=dict(traffic),actual_data_lane_byte_um=byte_um,
        region_directional_cuts=cuts,
        busiest_channel=dict(id=busiest,flits=flits.get(busiest,0),
            average_lane_service_fraction=flits.get(busiest,0)*result['spec']['noc_period_ps']/duration),
        source_pressure=network['final']['source_pressure_nodes'],
        gateway_queue_peak_bytes=max(native['gateway_queue_peak_bytes'].values(),default=0),
        native_reservation_stall_attempts=native['reservation_stall_attempts'],
        native_queue_rejection_attempts=native['queue_stall_attempts'],
        descriptor_pool_peak=max(native['pool_peak'].values(),default=0),
        control_admission_stall_attempts=native['request_control']['admission_stalls'],
        receiver_write_job_wait_sum_ps=network['rx_job_wait_sum_ps'],
        context_occupancy_ps=result['engine_context_ps'],
        contract='Actual native counters and executed directed channel traffic; cut rates use data-lane width, not sideband. '
            'Row classes are controller observations, not command traces. Average utilization and attempts do not identify critical-path stall. '
            'Controller read latency begins at native acceptance and excludes upstream waiting; per-job/context sums overlap.')
