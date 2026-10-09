"""Completed V3 execution evidence and matched hardware budget comparison."""
import argparse,gzip,json
from collections import Counter
from pathlib import Path
from w2w.architecture.serialization import from_record
from w2w.architecture.resources import inventory,matched_vertical_budget
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.io import write_json
from w2w.validation.vertical_access import audit_vertical_result


def analyze(source,external_reference=None):
    reg=json.loads((source/'registration.json').read_text())
    rows={};inputs={};records={}
    cases={case:(source,case_reg,reg) for case,case_reg in reg['cases'].items() if case!='external'}
    if external_reference is not None:
        external_reg=json.loads((external_reference/'registration.json').read_text())
        cases['external']=(external_reference,external_reg['cases']['external'],external_reg)
    elif 'external' in reg['cases'] and (source/'cases/external/completion.json').exists():
        cases['external']=(source,reg['cases']['external'],reg)
    for case,(case_source,case_reg,case_registration) in cases.items():
        data=json.loads((case_source/'inputs'/f'{case}.json').read_text())
        if digest(data)!=case_reg['input_sha256']:raise ValueError('Registered V3 input changed')
        path=case_source/'cases'/case
        completion=json.loads((path/'completion.json').read_text())
        if not completion['complete'] or completion['source_commit']!=case_registration['source_commit']:raise ValueError('Wrong completion identity')
        with gzip.open(path/'result.json.gz','rt') as f:r=json.load(f)
        audit=audit_vertical_result(r)
        if audit!=r['audit'] or r['graph']!=data['graph'] or r['spec']['stack']!=data['machine']:
            raise ValueError('Executed machine/graph does not match registered input')
        if completion['makespan_ps']!=r['makespan_ps']:raise ValueError('Completion timing differs from raw execution')
        capacity={m['id']:m['domain_ids'] for m in r['spec']['memories']}
        domain_bytes=Counter()
        for event in r['events']:
            if event['kind']!='read_issue':continue
            group=capacity[event['memory']];count=len(group)
            start=event['word_address']*count+event['bank']
            for bank,domain in enumerate(group):
                offset=(bank-start%count)%count
                words=max(0,(event['bytes']//32-offset+count-1)//count)
                domain_bytes[domain]+=words*32
        stack=from_record(data['machine']);native=r['native'];network=r['network']
        peak=max(domain_bytes.values(),default=0)
        interface_bound=peak*3760/16
        link=max(network['link_flits'],key=network['link_flits'].get,default=None)
        pressure=network.get('final',{}).get('source_pressure',{})
        pressure={k:v for k,v in pressure.items() if not k.endswith('_by_message')}
        rows[case]=dict(makespan_us=r['makespan_ps']/1e6,makespan_ps=r['makespan_ps'],audit=audit,
            source_commit=case_registration['source_commit'],input_sha256=case_reg['input_sha256'],
            logical_sha256=data['metadata']['logical_sha256'],weight_layout_sha256=data['metadata']['weight_layout_sha256'],
            compute_placement_sha256=data['metadata']['compute_placement_sha256'],
            macs=data['metadata']['macs'],vector_ops=data['metadata']['vector_ops'],
            native_config_sha256=native['config_sha256'],hop_flits=sum(network['link_flits'].values()),
            domain_weight_bytes=dict(domain_bytes),busiest_domain_bytes=peak,
            interface_only_necessary_bound_us=interface_bound/1e6,
            last_array_beat_tail_us=native['native_last_tail_ps']/1e6,
            last_gateway_native_ready_us=max(e['time_ps'] for e in r['events'] if e['kind']=='native_ready')/1e6,
            receive_write_max_service_us=max(network['rx_write_cycles'].values(),default=0)*r['spec']['noc_period_ps']/1e6,
            arithmetic_busy_max_us=max(r['compute_busy_ps'].values(),default=0)/1e6,
            engine_context_max_us=max(r['engine_context_ps'].values(),default=0)/1e6,
            critical_channel=link,critical_channel_flits=network['link_flits'].get(link,0),
            channel_service_fraction=network['link_flits'].get(link,0)*r['spec']['noc_period_ps']/r['makespan_ps'],
            source_pressure=pressure,gateway_busy_cycles=native['gateway_busy_cycles'],
            gateway_queue_peak_bytes=native['gateway_queue_peak_bytes'],
            native_reservation_stall_attempts=native['reservation_stall_attempts'],
            sram_peak_bytes=r['sram_peak_bytes'],resources=inventory(stack),
            resource_ledger_source='derived from frozen executed physical machine; includes gateway-router wires and finite cell metadata')
        inputs[case]=data;records[case]=r
    comparison=None
    if 'central' in rows and 'distributed' in rows:
        a,b=rows['central'],rows['distributed']
        for key in ('logical_sha256','weight_layout_sha256','compute_placement_sha256','macs','vector_ops','native_config_sha256'):
            if a[key]!=b[key]:raise ValueError(f'Unmatched {key}')
        if inputs['central']['graph']!=inputs['distributed']['graph']:raise ValueError('Execution plans differ across gateway comparison')
        proof=matched_vertical_budget(from_record(inputs['central']['machine']),from_record(inputs['distributed']['machine']))
        comparison=dict(budget=proof,completion_reduction_percent=100*(1-b['makespan_ps']/a['makespan_ps']),
            speedup=a['makespan_ps']/b['makespan_ps'],hop_flit_reduction_percent=100*(1-b['hop_flits']/a['hop_flits']),
            interpretation='joint gateway placement, physical collection, finite return pools and horizontal transport intervention; no isolated mechanism attribution')
    return dict(schema='w2w.vertical-access-analysis.v3',passed=True,source_commit=reg['source_commit'],
        cases=rows,comparison=comparison,external_comparison_cost_matched=False,
        limits=['single frozen one-token workload','coarse fine-to-macro network timing',
                'candidate DRAM/refresh and SRAM banking','full matrix staging and explicit conservative activation copies',
                'ideal global receive booking','one aggregate compute context per cluster','no numerical inference or PPA calibration'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--external-reference',type=Path,help='Separate corrected edge-I/O study; source identities remain separate')
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    report=analyze(args.source,getattr(args,'external_reference',None));write_json(args.output,report)
    print(json.dumps(dict(passed=True,cases={k:v['makespan_us'] for k,v in report['cases'].items()},comparison=report['comparison'])))


if __name__=='__main__':main()
