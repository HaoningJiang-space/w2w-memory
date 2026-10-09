"""Audit fixed placement runs and expose separate resource service/pressure measures."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path

from w2w.analysis.moe_layer import file_record,inspect
from w2w.analysis.residency_study import network_parameters
from w2w.common.fingerprints import digest_system_v2 as digest
from w2w.validation.system_execution import audit_system_result
from w2w.workloads.moe_partition import semantic_work


def pressure(result,metadata):
    tasks={t['id']:t for t in result['graph']['tasks']}
    memory,requester=Counter(),Counter()
    reads={}
    for e in result['events']:
        if e['kind']=='read_issue':
            memory[e['memory']]+=e['bytes'];requester[tasks[e['task']]['tile']]+=e['bytes']
            reads[e['request']]=e['task']
    network=result['network'];native=result['native'];duration=result['makespan_ps']
    edge_bytes=sum(e['size_bytes'] for e in result['graph']['data'])
    if (sum(result['sram_read_bytes'].values())!=edge_bytes
            or sum(network['rx_write_bytes'].values())!=edge_bytes+metadata['weight_read_bytes']):
        raise ValueError('SRAM read/write service bytes differ from application ledger')
    physical=result['wafer_machine'];links={l['id']:l for l in result['spec']['links']}
    cc=[p for p in physical['paths'] if links[next(l['id'] for l in links.values()
                                                  if l['resource_id']==p['resource_id'])]['kind']!='HB']
    sideband=network['cell_format']['sideband_bits']
    resources=dict(compute_engines=len(result['spec']['tiles']),memory_count=len(result['spec']['memories']),
        total_sram_bytes=sum(t['sram_bytes'] for t in result['spec']['tiles']),
        total_memory_bytes=sum(m['capacity_bytes'] for m in result['spec']['memories']),
        cc_data_wire_bit_mm=sum(p['data_wire_bit_mm'] for p in cc),
        cc_data_pipeline_bits=sum(p['link_register_bits'] for p in cc),
        cc_sideband_wire_bit_mm=sum(p['length_um']/1000*sideband for p in cc),
        cc_sideband_pipeline_bits=sum(p['data_cycles']*sideband for p in cc),
        cc_data_input_buffer_bytes=len(cc)*result['spec']['input_buffer_flits']*result['spec']['flit_bytes'],
        cc_sideband_input_buffer_bytes=len(cc)*result['spec']['input_buffer_flits']*sideband//8,
        native=native['resources'],area_um2=None,energy_j=None,
        receive_reservation=network['receive_reservation'],resource_density=physical['resource_density'])
    busiest=[]
    for link,count in network['link_flits'].items():
        l=links[link]
        if l['kind']=='HB':continue
        rtt=(l['pipeline_cycles']+l['credit_cycles'])*l['period_ps']
        bound=min(result['spec']['flit_bytes']*1000/l['period_ps'],
                  result['spec']['input_buffer_flits']*result['spec']['flit_bytes']*1000/rtt)
        busiest.append(dict(link=link,flits=count,busy_ps=count*l['period_ps'],
            utilization=count*l['period_ps']/duration,propagation_only_GBps_upper=bound))
    busiest.sort(key=lambda r:r['utilization'],reverse=True)
    last_weight=max((k for k,row in result['tasks'].items() if row['read_bytes']),
                    key=lambda k:result['tasks'][k]['finish_ps'])
    requests={k for k,t in reads.items() if t==last_weight}
    waits=network['final'].get('source_head_wait_by_packet',{})
    tail_waits={k:waits[k+'/resp'] for k in requests if k+'/resp' in waits}
    ports={tile:dict(bytes=network['rx_write_bytes'][tile],busy_cycles=cycles,
        service_us=cycles*result['spec']['noc_period_ps']/1e6,
        utilization=cycles*result['spec']['noc_period_ps']/duration,
        job_wait_sum_ps=network['rx_job_wait_sum_ps'].get(tile,0))
        for tile,cycles in network['rx_write_cycles'].items()}
    return dict(native=dict(peak_GBps_per_memory=native['resources']['interface_peak_GBps_per_memory'],
        peak_necessary_us=max(memory.values())/(native['resources']['interface_peak_GBps_per_memory']*1000),
        memory_read_bytes=dict(memory),queue_rejection_attempts=native['queue_stall_attempts'],
        reservation_stall_attempts=native['reservation_stall_attempts'],
        aggregation_peak_bytes=native['aggregation_peak_bytes'],
        last_rw_dl_hb_tail_ps=native['native_last_tail_ps']),
        owner_weight_reception=dict(bytes_by_tile=dict(requester),
            ideal_weight_write_bound_us=max(requester.values())*result['spec']['noc_period_ps']/
                result['spec']['rx_write_bytes_per_cycle']/1e6),
        receive_write_ports=ports,source_sram_read_ports=dict(bytes=result['sram_read_bytes'],
            busy_cycles=result['sram_read_busy_cycles'],width_bytes=result['activation_sram_read_bytes_per_cycle']),
        busiest_compute_links=busiest[:5],source_fifo=network['final'].get('source_pressure_nodes'),
        source_injected_flits=network['source_injected_flits'],
        compute_utilization={k:v/duration for k,v in result['compute_busy_ps'].items()},
        last_weight_task=last_weight,last_weight_task_source_waits=tail_waits,
        resources=resources,interpretation='busy service and separate overlapping queue/ready counters; do not sum them into a stall total')


def analyze(source):
    reg=json.loads((source/'registration.json').read_text())
    rows,proofs={},{}
    semantic,native_ids,network_ids,machines=set(),set(),set(),set()
    for case in reg['cases']:
        name=case['name'];directory=source/'cases'/name
        frozen=json.loads((source/'inputs'/(name+'.json')).read_text())
        done=json.loads((directory/'completion.json').read_text())
        summary=json.loads((directory/'summary.json').read_text())
        with gzip.open(directory/'result.json.gz','rt') as f:result=json.load(f)
        if (not done['complete'] or done['source_commit']!=reg['source_commit']
                or digest(frozen)!=case['input_sha256'] or done['input_sha256']!=case['input_sha256']
                or result['graph']!=frozen['graph'] or result['spec']!=frozen['spec']
                or result['wafer_machine']!=frozen['physical']
                or done['makespan_ps']!=result['makespan_ps'] or audit_system_result(result)!=result['audit']):
            raise ValueError('Run/input/byte/resource audit mismatch')
        native=result['native'];network=result['network']
        if (native['streaming']!=case['streaming'] or native['pending'] or native['upstream_pending']
                or native['reservations_live'] or native['completed_atoms']*16!=frozen['metadata']['weight_read_bytes']
                or network['local_dma_contract']!='payload_beats' or not network['final'].get('source_pressure')
                or network['cell_format']['sideband_bits']!=64):
            raise ValueError('Wrong native/transport contract or undrained resource')
        row=inspect(result,summary)
        semantic.add(digest(semantic_work(frozen['metadata'])))
        machines.add(digest(result['spec']));native_ids.add(digest(row['native_identity']))
        parameters,files=network_parameters(directory,network['identity'])
        network_ids.add(digest(parameters))
        array_last={e['request']:e for e in result['events'] if e['kind']=='array_last_ready'}
        ready={e['request']:e['time_ps'] for e in result['events'] if e['kind']=='native_ready'}
        if set(array_last)!=set(ready) or any(
                e['beat_tail_ps']!=e['time_ps']+3760 or e['beat_tail_ps']>ready[k] for k,e in array_last.items()):
            raise ValueError('Array ready, RWDL/HB tail and controller-ready boundary differ')
        row.update(architecture=case['architecture'],streaming=case['streaming'],
            semantic_work_sha256=case['semantic_work_sha256'],pressure=pressure(result,frozen['metadata']),
            wall_seconds=summary['wall_seconds'],kernel_iterations=result['kernel_iterations'],
            total_compute_busy_ps=sum(result['compute_busy_ps'].values()),
            extra_reduce_vector_ops=frozen['metadata'].get('additional_reduction_vector_ops',0))
        rows[name]=row
        proofs[name]={p:file_record(directory/p) for p in ('result.json.gz','summary.json','completion.json')}
        proofs[name].update({str(p.relative_to(directory)):file_record(p) for p in files})
        del result
    if any(len(v)!=1 for v in (semantic,native_ids,network_ids,machines)):
        raise ValueError('Cases changed semantic work, native configuration or shared wafer resources')
    a,b=rows['gather-stream'],rows['gather-whole']
    if a['graph_sha256']!=b['graph_sha256'] or a['pressure']['receive_write_ports'].keys()!=b['pressure']['receive_write_ports'].keys():
        raise ValueError('Readiness contrast changed graph or receiver set')
    for tile,p in a['pressure']['receive_write_ports'].items():
        if p['busy_cycles']!=b['pressure']['receive_write_ports'][tile]['busy_cycles']:
            raise ValueError('Whole/streaming consumed different SRAM write service')
    return dict(schema='w2w.compute-placement-analysis.v1',source_commit=reg['source_commit'],passed=True,
        scope=reg['scope'],cases=rows,raw_result_provenance=proofs,
        near_shard_completion_reduction_percent=100*(1-rows['near-shard-stream']['makespan_us']/a['makespan_us']),
        stream_completion_change_vs_whole_percent=100*(a['makespan_us']/b['makespan_us']-1),
        interpretation='Fixed uncalibrated resource reference and ideal receive reservation; tensor partition changes graph, not hardware capacity')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();value=analyze(args.source)
    args.output.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:r['makespan_us'] for k,r in value['cases'].items()}))


if __name__=='__main__':main()
