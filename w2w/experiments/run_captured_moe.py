"""Registered long real-request MoE replay on the unchanged physical executor.

Every captured prefill/decode token in selected real layers is executed. This
is explicitly post-router MoE timing, not complete Transformer inference.
"""
import argparse,gzip,json,os,time
from dataclasses import asdict
from pathlib import Path
from w2w.common.io import write_json
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.provenance import revision
from w2w.workloads.moe_trace import file_sha
from w2w.mapping.captured_sequence import lower_captured_request
from w2w.architecture.presets.recipes import from_recipe
from w2w.architecture.compiler import compile_machine
from w2w.architecture.resources import inventory
from w2w.system.weight_cache import WeightCacheConfig

CASES=('reference_compute','up_local_compute')


def inputs(capture,case,layer_keys):
    if case not in CASES:raise ValueError('Unknown co-placement policy')
    machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'))
    graph,meta=lower_captured_request(capture,machine,layer_keys,projection_policy=case)
    cache=WeightCacheConfig(initial_resident=())
    data=dict(machine=asdict(machine.stack),graph=asdict(graph),metadata=meta,cache=asdict(cache),
        resources=inventory(machine.stack),projection_policy=case,request_id=capture['request_id'],
        capture_sha256=digest(capture),network_policy=dict(ready_router_ids=tuple(r.id for r in machine.routers),ready_slots=16),
        compute_contexts=2,fetch_contexts=2,operand_readiness='contiguous_prefix',read_issue_policy='round_robin',
        scope=meta['scope'],initialization='Empty finite cache: no pretrained/initial weight residency, no free startup.',
        arrival_contract='One captured request, sequential prefill then decode; source wall-clock timing is not captured.')
    return machine,graph,cache,data


def prepare(root,corpus,index,layer_keys):
    if index<0:raise ValueError('Nonnegative fixed manifest index required')
    manifest=json.loads((corpus/'manifest.json').read_text());audit=json.loads((corpus/'coverage-audit.json').read_text())
    if not audit['passed'] or file_sha(corpus/'manifest.json')!=audit['normalized_manifest_sha256']:
        raise ValueError('Complete corpus audit required before registering execution')
    row=manifest['requests'][index];path=corpus/row['path']
    if file_sha(path)!=row['file_sha256']:raise ValueError('Captured request changed')
    capture=json.load(gzip.open(path,'rt'))
    if digest(capture)!=row['normalized_sha256']:raise ValueError('Captured routing content changed')
    root.mkdir(parents=True,exist_ok=False);(root/'inputs').mkdir()
    with gzip.open(root/'capture.json.gz','wt') as f:json.dump(capture,f)
    rows={};previous=None
    for case in CASES:
        _,_,_,data=inputs(capture,case,layer_keys)
        with gzip.open(root/'inputs'/f'{case}.json.gz','wt') as f:json.dump(data,f)
        rows[case]=dict(input_sha256=digest(data),graph_sha256=digest(data['graph']),tasks=len(data['graph']['tasks']))
        identity=[(t['id'],t['compute_cycles'],t['reads'],t['scratch_bytes'],t['stream']) for t in data['graph']['tasks']]
        common=(data['machine'],data['resources'],data['cache'],data['graph']['objects'],data['graph']['data'],
            data['graph']['control'],identity)
        if previous is not None and previous!=common:raise ValueError('Comparison changed math, addresses, dependencies or resources')
        previous=common
    write_json(root/'registration.json',dict(schema='w2w.captured-moe-study.v1',source_commit=revision(),cases=rows,
        selection='First manifest request by pre-existing source order; original layers explicitly named, no performance selection',
        manifest_index=index,request_id=row['id'],raw_sha256=row['raw_sha256'],capture_sha256=digest(capture),
        corpus_manifest_sha256=file_sha(corpus/'manifest.json'),corpus_audit_sha256=file_sha(corpus/'coverage-audit.json'),
        dataset_revision=manifest['dataset_revision'],model_source=manifest['model_source'],layer_keys=layer_keys,
        captured_layers=capture['shape']['layers'],execution_omitted_layers=capture['shape']['layers']-len(layer_keys),
        prefill_tokens=capture['coverage']['prefill_tokens'],decode_tokens=capture['coverage']['decode_tokens'],
        execution_omitted_tokens=0,max_ps=600000000000,
        full_model_expert_catalog_bytes=capture['shape']['layers']*data['metadata']['catalog_weight_bytes']//len(layer_keys),
        selected_expert_catalog_bytes=data['metadata']['catalog_weight_bytes'],physical_dram_bytes=data['resources']['native']['capacity_bytes'],
        scope=data['scope'],contract='Two paid fetch slots and contexts, shared MAC/read, finite empty cache, Native refresh/control/NoC. '
            'Every selected real layer uses its own captured routing. Complete request phases; no smoke token/shape reduction. '
            'Selected-layer replay is not full-model execution. No performance filtering, automatic retries or new hardware.'))


def run(root,case,binary):
    from w2w.system.kernel import execute_system
    from w2w.backends.ramulator import VerticalRWDL
    from w2w.backends.booksim.adapter import factory
    from w2w.validation.vertical_access import audit_vertical_result
    from w2w.validation.request_control import audit_request_control
    reg=json.loads((root/'registration.json').read_text());capture=json.load(gzip.open(root/'capture.json.gz','rt'))
    machine,graph,cache,data=inputs(capture,case,reg['layer_keys'])
    if revision()!=reg['source_commit'] or digest(data)!=reg['cases'][case]['input_sha256']:
        raise ValueError('Registered source/input changed')
    directory=root/'cases'/case;directory.mkdir(parents=True,exist_ok=False);start=time.monotonic()
    finishes={t:i for i in data['metadata']['invocations'] for t in i['finish_tasks']}
    def observe(e):
        if e['kind']=='task_finish' and e['task'] in finishes:
            i=finishes[e['task']]
            print(json.dumps(dict(task=e['task'],phase=i['phase'],step=i['decode_step'],layer=i['captured_layer'],
                time_ps=e['time_ps'],wall_seconds=time.monotonic()-start)),flush=True)
    native=VerticalRWDL(machine,request_control=True,refresh=True,gateway_trace_bin_ps=1000000)
    try:
        r=execute_system(machine,graph,native=native,compute_contexts=2,fetch_contexts=2,read_issue_policy='round_robin',
            operand_readiness='contiguous_prefix',weight_cache=cache,event_observer=observe,time_advance='boundaries',
            max_ps=reg['max_ps'],activation_sram_read_bytes_per_cycle=machine.rx_write_bytes_per_cycle,
            network_factory=factory(binary=binary,directory=directory/'network',**data['network_policy']))
    finally:native.close()
    a=audit_vertical_result(r);b=audit_request_control(r)
    if sum(e.get('macs',0) for e in r['events'] if e['kind']=='stream_compute')!=data['metadata']['macs']:
        raise ValueError('Captured MoE arithmetic work changed')
    actual={e['task'] for e in r['events'] if e['kind']=='task_finish'}
    if actual!={t.id for t in graph.tasks}:raise ValueError('Complete captured MoE task execution required')
    r['source_commit']=revision()
    with gzip.open(directory/'result.json.gz','wt',compresslevel=3) as f:json.dump(r,f)
    write_json(directory/'completion.json',dict(complete=True,source_commit=revision(),input_sha256=digest(data),
        case=case,makespan_ps=r['makespan_ps'],drained_ps=r['drained_ps'],wall_seconds=time.monotonic()-start,
        audit=a,control_audit=b,completed_tasks=len(actual),completed_invocations=len(data['metadata']['invocations']),
        booksim_sha256=r['network']['identity']['binary_sha256'],bridge_sha256=r['native']['bridge_sha256'],scope=data['scope']))
    print(json.dumps(dict(complete=True,case=case,makespan_ps=r['makespan_ps'])),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--case',choices=CASES)
    p.add_argument('--corpus',type=Path);p.add_argument('--index',type=int,default=0);p.add_argument('--layers',nargs='+',default=['0','1'])
    p.add_argument('--booksim-binary',type=Path,default=os.getenv('W2W_BOOKSIM_BINARY'));a=p.parse_args()
    if a.prepare:
        if a.corpus is None:p.error('Audited complete corpus required')
        prepare(a.output,a.corpus,a.index,tuple(a.layers))
    else:
        if a.booksim_binary is None:p.error('Native binary required')
        run(a.output,a.case,a.booksim_binary)


if __name__=='__main__':main()
