"""Re-audit registered raw results; no simulator execution or automatic reruns."""
import argparse,gzip,json
from pathlib import Path
from w2w.common.io import write_json
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.architecture.resources import matched_vertical_budget
from w2w.architecture.serialization import from_record
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control


def analyze(source):
    registration=json.loads((source/'registration.json').read_text());rows={};inputs={};native_config=set()
    for case,identity in registration['cases'].items():
        path=source/'inputs'/f'{case}.json'
        data=json.loads(path.read_text()) if path.exists() else json.load(gzip.open(path.with_suffix('.json.gz'),'rt'))
        if digest(data)!=identity['input_sha256']:raise ValueError('Input fingerprint differs from registration')
        directory=source/'cases'/case;completion=json.loads((directory/'completion.json').read_text())
        if not completion['complete'] or completion['source_commit']!=registration['source_commit']:raise ValueError('Wrong source/completion identity')
        result=json.load(gzip.open(directory/'result.json.gz','rt'));audit=audit_vertical_result(result)
        control=audit_request_control(result)
        if result['graph']!=data['graph'] or result['spec']['stack']!=data['machine'] or audit!=completion['audit']:
            raise ValueError('Executed graph, physical stack or conservation differs')
        if result['makespan_ps']!=completion['makespan_ps'] or result['source_commit']!=registration['source_commit']:
            raise ValueError('Raw time/source does not match completion')
        policy=data['network_policy'];arbiter=result['network']['source_arbiter']
        if arbiter['routers']!=sorted(policy['ready_router_ids']) or arbiter['additional_metadata_bits']!=len(policy['ready_router_ids'])*policy['ready_slots']*96:
            raise ValueError('Selector policy/cost differs from registration')
        if result['compute_execution']['contexts_per_cluster']!=data['compute_contexts']:
            raise ValueError('Compute execution policy changed')
        native_config.add(result['native']['config_sha256'])
        pressure=result['network']['final']['source_pressure']
        row=dict(source_commit=registration['source_commit'],input_sha256=identity['input_sha256'],makespan_ps=result['makespan_ps'],makespan_us=result['makespan_ps']/1e6,
            audit=audit,control_audit=control,hop_flits=sum(result['network']['link_flits'].values()),
            last_native_tail_ps=result['native']['native_last_tail_ps'],
            max_rx_service_ps=max(result['network']['rx_write_cycles'].values(),default=0)*result['spec']['noc_period_ps'],
            max_arithmetic_busy_ps=max(result['compute_busy_ps'].values(),default=0),
            compute_execution=result['compute_execution'],source_arbiter=arbiter,
            ready_behind_credit_source_cycles=sum(pressure['ready_behind_with_injection_credit_cycles']),
            binary_sha256=result['network']['identity']['binary_sha256'])
        if 'weight_cache' in result:
            cache=result['weight_cache'];row['weight_cache']=cache;row['request_control']=result['native']['request_control']
            if cache['data_bytes_per_cluster']!=data['cache']['data_bytes_per_cluster'] or cache['initial_resident_bytes']!=data['metadata']['initial_resident_bytes']:
                raise ValueError('Weight cache/warm state differs')
            row['active_unique_weight_bytes']=data['metadata']['active_unique_weight_bytes']
            row['logical_weight_read_bytes']=data['metadata']['logical_weight_read_bytes']
            row['invocations']=completion['invocations']
        rows[case]=row;inputs[case]=data
        del result
    if len(native_config)!=1:raise ValueError('Native array/controller policy differs')
    a='central-fifo' if 'central-fifo' in rows else 'central-plus-two-layer';b='distributed-fifo' if 'distributed-fifo' in rows else 'distributed-two-layer'
    for key in ('graph','metadata','compute_contexts'):
        if inputs[a][key]!=inputs[b][key]:raise ValueError('Compared work/placement changed')
    proof=matched_vertical_budget(from_record(inputs[a]['machine']),from_record(inputs[b]['machine']))
    comparison=dict(budget=proof,completion_reduction_percent=100*(1-rows[b]['makespan_ps']/rows[a]['makespan_ps']))
    if 'central-plus' in rows:
        if any(inputs[a][k]!=inputs['central-plus'][k] for k in ('machine','graph','resources','compute_contexts')):raise ValueError('Central+ physical change')
        comparison['central_plus_reduction_percent']=100*(1-rows['central-plus']['makespan_ps']/rows[a]['makespan_ps'])
        comparison['distributed_vs_central_plus_reduction_percent']=100*(1-rows[b]['makespan_ps']/rows['central-plus']['makespan_ps'])
    else:
        if any(inputs[a][k]!=inputs[b][k] for k in ('cache','routing','request_control','network_policy')):raise ValueError('Hierarchy policies changed')
    return dict(schema='w2w.gateway-hierarchy-analysis.v1',passed=True,source_commit=registration['source_commit'],cases=rows,comparison=comparison,
        limits=['finite aggregate contexts, not a product-cycle model','ideal global receive booking','candidate array timing and SRAM banking',
            'two-layer routing reuse is a proxy when used; initialization outside warm interval','resource proxies, no calibrated PPA','no numerical inference'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    report=analyze(args.source);write_json(args.output,report)
    print(json.dumps(dict(passed=True,cases={k:v['makespan_us'] for k,v in report['cases'].items()},comparison=report['comparison'])))

if __name__=='__main__':main()
