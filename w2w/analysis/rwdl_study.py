"""Independent complete-layer evidence and resource ledger; no simulator runs."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path

from w2w.analysis.moe_layer import digest, file_record, inspect
from w2w.analysis.residency_study import network_parameters
from w2w.workloads.semantics import logical_work
from w2w.validation.system_execution import audit_system_result


def cost(record, resources):
    # Controller-ready runs do not execute the legacy HB placeholder links.
    cc=[p for p in record['physical']['paths'] if not any(
        l['kind']=='HB' and l['resource_id']==p['resource_id'] for l in record['spec']['links'])]
    fields=('data_wire_bit_mm','link_register_bits','credit_wire_bit_mm','credit_register_bits')
    memories=len(record['spec']['memories'])
    return dict(compute_network={k:sum(p[k] for p in cc) for k in fields},
        native_data_lanes=memories*resources['data_lanes_per_memory'],
        native_hb_data_wire_bit_mm=memories*resources['data_lanes_per_memory']*
            record['physical']['recipe']['hb_height_um']/1000,
        native_reserved_return_bytes=memories*resources['shared_return_reservation_bytes_per_memory'],
        descriptor_return_bytes=memories*resources['descriptor_return_bytes_per_memory'],
        native_read_queue_entries=memories*resources['command_read_entries_per_memory'],
        native_active_entries=memories*32,refresh_priority_entries=memories*32,
        digital_controller_instances=memories*32, aggregation_mux_input_bits_per_memory=4096,
        aggregation_port_bits_per_memory=resources['aggregation_bits'],
        array_control_wire_bits=None,controller_area_um2=None,energy_j=None,
        physical_scope='resource proxies only; HB/RWDL same lanes counted once; unused legacy HB placeholders excluded')


def analyze(source):
    reg=json.loads((source/'registration.json').read_text())
    records,proofs={},{}
    signatures=set()
    native_signatures=set()
    network_signatures=set()
    for case in reg['cases']:
        name=case['name']
        frozen=json.loads((source/'inputs'/(name+'.json')).read_text())
        if digest(frozen)!=case['input_sha256']:
            raise ValueError('Frozen input changed')
        directory=source/'cases'/name
        done=json.loads((directory/'completion.json').read_text())
        summary=json.loads((directory/'summary.json').read_text())
        with gzip.open(directory/'result.json.gz','rt') as f:result=json.load(f)
        if (not done['complete'] or done['source_commit']!=reg['source_commit']
                or done['input_sha256']!=case['input_sha256']
                or result['graph']!=frozen['graph'] or result['spec']!=frozen['spec']
                or result['wafer_machine']!=frozen['physical']
                or done['makespan_ps']!=result['makespan_ps']):
            raise ValueError('Run differs from registration')
        audit=audit_system_result(result)
        native=result['native']
        if (audit!=result['audit'] or native['kind']!='ramulator_rwdl_candidate_v1'
                or native['pending'] or native['upstream_pending'] or native['reservations_live']
                or native['completed_atoms']*16!=frozen['metadata']['weight_read_bytes']
                or native['accepted_atoms']!=native['completed_atoms']
                or max(native['reservation_peak_atoms'].values())>8
                or max(native['aggregation_peak_bytes'].values())>4096):
            raise ValueError('RWDL byte/reservation audit failed')
        signatures.add(digest(logical_work(result['graph'])))
        row=inspect(result,summary)
        native_signatures.add(digest(row['native_identity']))
        parameters,files=network_parameters(directory,result['network']['identity'])
        network_signatures.add(digest(parameters))
        baseline=reg['baseline']
        if result['network']['identity']['binary_sha256']!=baseline['network_identity']['binary_sha256']:
            raise ValueError('Network executable changed from archived HBM2')
        ready={e['request']:e['time_ps'] for e in result['events'] if e['kind']=='native_ready'}
        supply={e['packet'][:-5]:e['time_ps'] for e in result['events'] if e['kind']=='response_first_supply'}
        rx=Counter()
        for e in result['events']:
            if e['kind']=='read_issue':
                task=next(t for t in result['graph']['tasks'] if t['id']==e['task'])
                rx[task['tile']]+=e['bytes']
        row.update(policy=case['policy'],layout_sha256=case['layout_sha256'],
            logical_work_sha256=case['logical_work_sha256'],
            native_last_ready_ps=max(ready.values()),drained_ps=result['drained_ps'],
            streaming_progress=dict(supplied_descriptors=len(supply),
                supply_before_full_native=sum(t<ready[k] for k,t in supply.items())),
            native_peak_bandwidth_necessary_bound_us=max(row['memory_read_bytes'].values())/
                (native['resources']['interface_peak_GBps_per_memory']*1000),
            requester_rx_necessary_bound_us=max(rx.values())/256000,
            native_service=native,resource_ledger=cost(frozen,native['resources']),
            wall_seconds=summary['wall_seconds'],kernel_iterations=result['kernel_iterations'])
        if case['policy']=='four_way' and row['graph_sha256']!=baseline['graph_sha256']:
            raise ValueError('Four-way changed archived HBM2 graph')
        proofs[name]={p:file_record(directory/p) for p in ('result.json.gz','summary.json','completion.json')}
        proofs[name].update({str(p.relative_to(directory)):file_record(p) for p in files})
        records[name]=row
        del result
    if len(signatures)!=1 or len(native_signatures)!=1 or len(network_signatures)!=1:
        raise ValueError('Cases changed logical work, native configuration, or network')
    base=records['rwdl-four_way']['makespan_us']
    home=records['rwdl-home']['makespan_us']
    return dict(schema='w2w.rwdl-analysis.v1',source_commit=reg['source_commit'],
        scope=reg['scope'],passed=True,baseline_rerun=False,baseline=reg['baseline'],cases=records,
        home_completion_change_vs_four_way_percent=100*(home/base-1),
        raw_result_provenance=proofs,
        interpretation='Different memory organizations; native peak alone does not establish bottleneck migration; uncalibrated resource proxies')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    value=analyze(args.source)
    args.output.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:dict(makespan_us=v['makespan_us'],native_bound_us=v['native_peak_bandwidth_necessary_bound_us'],
        busiest_links=v['busiest_compute_links']) for k,v in value['cases'].items()},indent=2))


if __name__=='__main__':main()
