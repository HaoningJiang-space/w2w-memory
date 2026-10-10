"""Separate Up compute/weight co-placement gate on unchanged native execution."""
import argparse,gzip,json,os,time
from dataclasses import asdict
from pathlib import Path
from w2w.experiments.run_static_placement import inputs as original_inputs
from w2w.workloads.routing_input import load_workload
from w2w.mapping.compute_placement import place_projection_compute,PROJECTION_POLICIES
from w2w.mapping.lowering import lower
from w2w.mapping.sequence import lower_sequence
from w2w.analysis.placement_screen import screen
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.io import write_json
from w2w.provenance import revision
from w2w.system.weight_cache import WeightCacheConfig
from w2w.system.kernel import execute_system
from w2w.backends.ramulator import VerticalRWDL
from w2w.backends.booksim.adapter import factory
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control
from w2w.validation.co_placement import audit_co_placement_inputs


def inputs(policy,mode):
    if policy not in PROJECTION_POLICIES or mode=='multilayer' and policy=='up_matched_nonlocal':
        raise ValueError('Unknown/cold-only compute intervention')
    machine,graph,cache,data=original_inputs('phase-split',mode,'s1')
    old_sha=digest(data)
    if policy!='reference_compute':
        from w2w.mapping.data_placement import WeightLocation
        weights=tuple(WeightLocation(**w) for w in data['weights'])
        reference=tuple(WeightLocation(**w) for w in data['compute_reference_weights'])
        if mode=='cold':
            logical=load_workload('configs/workloads/c0_b1.json')
            placement=place_projection_compute(logical,machine.stack,reference,weights,policy)
            graph,meta=lower(logical,machine,weights,placement,execution_policy='s1')
        else:
            routing=data['routing']
            graph,meta,preload=lower_sequence(routing['token_experts'],machine,layers=routing['layers'],shape=routing['shape'],
                weight_layout=weights,compute_reference=reference,execution_policy='s1',projection_policy=policy)
            cache=WeightCacheConfig(initial_resident=preload)
        data.update(graph=asdict(graph),metadata=meta,cache=None if cache is None else asdict(cache))
        if mode=='cold':data['screen']=screen(machine,graph,meta)
    data.pop('static_policy_contract')
    data.update(projection_policy=policy,
        co_placement_contract='Phase-Split weight addresses fixed; Gate/Activation/Down/accumulate/reduce/input/combine fixed; only Up execution changes. '
            'Same existing compute data resources, S1 two coupled fetch slots, shared ports and finite SRAM. '
            'Matched nonlocal is a cold workload-known mechanism diagnostic, not a proposed static placement policy.')
    if policy=='reference_compute':data['legacy_input_sha256']=old_sha
    return machine,graph,cache,data


def prepare(root,mode):
    policies=PROJECTION_POLICIES if mode=='cold' else PROJECTION_POLICIES[:2]
    data={case:inputs(case,mode)[3] for case in policies};proof=audit_co_placement_inputs(data)
    root.mkdir(parents=True,exist_ok=False);(root/'inputs').mkdir();rows={}
    for case,row in data.items():
        with gzip.open(root/'inputs'/f'{case}.json.gz','wt') as f:json.dump(row,f)
        rows[case]=dict(input_sha256=digest(row),graph_sha256=digest(row['graph']),screen=row.get('screen'))
    write_json(root/'registration.json',dict(schema='w2w.co-placement-study.v1',source_commit=revision(),mode=mode,cases=rows,
        input_audit=proof,max_ps=60000000000 if mode=='multilayer' else 6000000000,
        contract='No kernel/native/topology changes; whole matrices, real X/U DataEdges. Fixed Phase-Split weights with reference, Up-local '
            'and cold per-cluster-work-matched nonlocal compute. Full-catalog warm Up preload follows its real consumer; initialization excluded and reported. '
            'No performance-dependent retry, activation broadcast/alias optimization, fragment or additional service resources.'))


def run(root,case,binary):
    reg=json.loads((root/'registration.json').read_text());machine,graph,cache,data=inputs(case,reg['mode'])
    if revision()!=reg['source_commit'] or digest(data)!=reg['cases'][case]['input_sha256']:raise ValueError('Registered source/input changed')
    directory=root/'cases'/case;directory.mkdir(parents=True,exist_ok=False);start=time.monotonic()
    native=VerticalRWDL(machine,request_control=True,refresh=True,gateway_trace_bin_ps=1000000)
    markers={x['finish_task']:x for x in data['metadata'].get('invocations',())}
    def observe(e):
        if e['kind']=='task_finish' and (e['task'] in markers or e['task'].endswith('/accumulate')):
            print(json.dumps(dict(task=e['task'],invocation=markers.get(e['task']),time_ps=e['time_ps'],wall_seconds=time.monotonic()-start)),flush=True)
    try:
        r=execute_system(machine,graph,native=native,compute_contexts=2,fetch_contexts=2,read_issue_policy='round_robin',
            operand_readiness='contiguous_prefix',weight_cache=cache,event_observer=observe,time_advance='boundaries',
            max_ps=reg['max_ps'],activation_sram_read_bytes_per_cycle=machine.rx_write_bytes_per_cycle,
            network_factory=factory(binary=binary,directory=directory/'network',**data['network_policy']))
    finally:native.close()
    r['source_commit']=revision();a=audit_vertical_result(r);b=audit_request_control(r)
    if sum(e.get('macs',0) for e in r['events'] if e['kind']=='stream_compute')!=data['metadata']['macs']:
        raise ValueError('Co-placement changed arithmetic work')
    with gzip.open(directory/'result.json.gz','wt',compresslevel=3) as f:json.dump(r,f)
    write_json(directory/'completion.json',dict(complete=True,source_commit=revision(),input_sha256=digest(data),case=case,
        makespan_ps=r['makespan_ps'],drained_ps=r['drained_ps'],wall_seconds=time.monotonic()-start,
        audit=a,control_audit=b,booksim_sha256=r['network']['identity']['binary_sha256'],bridge_sha256=r['native']['bridge_sha256']))
    print(json.dumps(dict(case=case,complete=True,makespan_ps=r['makespan_ps'])),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    actions=p.add_mutually_exclusive_group(required=True);actions.add_argument('--prepare',action='store_true');actions.add_argument('--case',choices=PROJECTION_POLICIES)
    p.add_argument('--mode',choices=('cold','multilayer'),default='cold');p.add_argument('--booksim-binary',type=Path,default=os.getenv('W2W_BOOKSIM_BINARY'));a=p.parse_args()
    if a.prepare:prepare(a.output,a.mode)
    else:run(a.output,a.case,a.booksim_binary)


if __name__=='__main__':main()
