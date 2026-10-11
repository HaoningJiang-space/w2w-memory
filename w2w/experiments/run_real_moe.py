"""Registered full real-cohort MoE replay, bounded two-layer physical windows."""
import argparse,gzip,json,os,time
from dataclasses import asdict
from collections import defaultdict
from pathlib import Path
from w2w.workloads.patterns_adapter import load_corpus,observations
from w2w.workloads.moe_trace import file_sha
from w2w.serving.batcher import group
from w2w.architecture.presets.recipes import from_recipe
from w2w.architecture.compiler import compile_machine
from w2w.architecture.resources import inventory
from w2w.architecture.npu_profile import reference_profile
from w2w.mapping.moe_batch_lowering import full_catalog,lower_batch,BASELINES
from w2w.domain.execution import ExecutionGraph,ControlEdge,DataEdge
from w2w.system.npu_kernel import NPUKernelModel
from w2w.system.runtime_windows import RuntimeWindows
from w2w.system.weight_cache import WeightCacheConfig
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.io import write_json
from w2w.provenance import revision


def select_cohort(captures,B):
    subjects=defaultdict(list)
    for c in captures:subjects[c['request_id'].split('/')[-2]].append(c)
    if len(subjects)!=8 or B not in (1,4,16,32):raise ValueError('Registered 8-subject/B contract required')
    chosen=[]
    for n in range(4):
        for members in subjects.values():chosen.append(members[n])
    selected={c['request_id'] for c in chosen[:B]}
    return tuple(c for c in captures if c['request_id'] in selected)


def paired_batches(cohort,layers,prefill_microbatch):
    tokens=[(c,i) for c in cohort for i in range(c['coverage']['prefill_tokens'])]
    for start in range(0,len(tokens),prefill_microbatch):
        subset=tokens[start:start+prefill_microbatch]
        yield tuple(group(f'prefill/C{start//prefill_microbatch}/L{l}',
            tuple(observations(c,'prefill',l)[i] for c,i in subset)) for l in layers)
    counts={c['coverage']['decode_tokens'] for c in cohort}
    if len(counts)!=1:raise ValueError('Complete captured lifecycle required')
    for step in range(next(iter(counts))):
        yield tuple(group(f'decode/S{step}/L{l}',tuple(observations(c,'decode',l,step)[0] for c in cohort)) for l in layers)


def physical_windows(cohort,machine,catalog,profile,layers,prefill_microbatch):
    for index,batches in enumerate(paired_batches(cohort,layers,prefill_microbatch)):
        tasks=[];data=[];control=[];kernels={};calls=[];previous=[]
        for batch in batches:
            prefix=f'W{index:04d}/L{batch.layer_id}/'
            g,k,meta=lower_batch(batch,machine,catalog,profile,prefix=prefix)
            inputs=[prefix+f't{t}/input' for t in range(batch.token_count)]
            if previous:
                for producer in previous:
                    for consumer in inputs:control.append(ControlEdge(producer,consumer))
                for t,(producer,consumer) in enumerate(zip(previous,inputs)):
                    data.append(DataEdge(prefix+f'layer_activation/{t}',producer,consumer,catalog['shape']['hidden']*2))
            tasks.extend(g.tasks);data.extend(g.data);control.extend(g.control);kernels.update(k)
            calls.append({key:meta[key] for key in ('batch_id','layer_id','token_ids','token_to_experts','expert_token_counts',
                'expert_macs','router_macs','router_vector_ops','finish_tasks','router_visibility','scratch_policy')})
            previous=meta['finish_tasks']
        meta=dict(index=index,calls=calls,npu_kernels={k:asdict(v) for k,v in kernels.items()},
            expert_macs=sum(c['expert_macs'] for c in calls),router_macs=sum(c['router_macs'] for c in calls))
        yield ExecutionGraph(tuple(tasks),catalog['objects'],tuple(data),tuple(control)),kernels,meta


def prepare(root,corpus,gate_receipts=()):
    captures=tuple(load_corpus(corpus));root.mkdir(parents=True,exist_ok=False);(root/'cohorts').mkdir()
    machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'));p=reference_profile()
    rows={};cohorts={};layers=('0','1');shape=captures[0]['shape']
    gates=[]
    for path in gate_receipts:
        if json.loads(Path(path).read_text()).get('passed') is not True:raise ValueError('Unpassed kernel/carry/equivalence gate')
        gates.append(dict(path=str(Path(path).resolve()),sha256=file_sha(path)))
    for B in (1,4,16,32):
        selected=select_cohort(captures,B);path=root/'cohorts'/f'B{B}.json.gz'
        with gzip.open(path,'wt') as f:json.dump(selected,f)
        cohorts[str(B)]=dict(file=path.name,sha256=file_sha(path),request_ids=[c['request_id'] for c in selected],
            original_request_hashes={c['request_id']:c['raw_sha256'] for c in selected},
            prefill_tokens=sum(c['coverage']['prefill_tokens'] for c in selected),decode_steps=128,
            captured_layers=94,executed_layers=list(layers),omitted_execution_layers=92,omitted_execution_tokens=0)
        for baseline in BASELINES:
            catalog=full_catalog(machine,shape,layers,baseline)
            rows[f'B{B}-{baseline}']=dict(B=B,baseline=baseline,catalog_sha256=digest([asdict(o) for o in catalog['objects']]),
                resident_catalog_bytes=sum(o.size_bytes for o in catalog['objects']))
    write_json(root/'registration.json',dict(schema='w2w.real-npu-moe-study.v1',source_commit=revision(),cases=rows,cohorts=cohorts,
        corpus_manifest_sha256=file_sha(corpus/'manifest.json'),coverage_audit_sha256=file_sha(corpus/'coverage-audit.json'),
        shape=shape,layers=list(layers),prefill_microbatch=32,npu_profile=asdict(p),machine_sha256=digest(asdict(machine)),
        resources=inventory(machine.stack),cache=asdict(WeightCacheConfig()),max_ps=2000000000000,kernel_gate_receipts=gates,
        selection='Before performance: first four source-order requests per each of eight original subjects, interleaved only for selection; retained cohort order is original manifest order. B cohorts are nested, no route/performance selection.',
        scope='Complete captured prefill and all 128 decode steps for each registered cohort; two true adjacent layers, explicit modeled router/pack/scatter/combine and shape-aware OS NPU. Not full Transformer latency.',
        contract='All three legal mappings share the same NPU/compute/DRAM/HB/NoC/cache budgets. '
            'Only current two-layer batch window is instantiated. Native clocks/refresh/row state, BookSim/credits and LRU persist across windows. '
            'No cache shrinking, fabricated router values/arrival times, token truncation or automatic retries. BF16 router weights are a declared uncached timing format.'))


def run(root,case,binary):
    from w2w.system.kernel import execute_system
    from w2w.backends.ramulator import VerticalRWDL
    from w2w.backends.booksim.adapter import factory
    reg=json.loads((root/'registration.json').read_text());choice=reg['cases'][case]
    if len(reg.get('kernel_gate_receipts',[]))<5:raise ValueError('Independent shape, compute, Native, continuous-state and event-equivalence gates required')
    for receipt in reg['kernel_gate_receipts']:
        if file_sha(receipt['path'])!=receipt['sha256']:raise ValueError('Accepted kernel gate receipt changed')
    if revision()!=reg['source_commit']:raise ValueError('Frozen source changed')
    path=root/'cohorts'/reg['cohorts'][str(choice['B'])]['file']
    if file_sha(path)!=reg['cohorts'][str(choice['B'])]['sha256']:raise ValueError('Complete real cohort changed')
    cohort=tuple(json.load(gzip.open(path,'rt')))
    machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'));profile=reference_profile()
    if digest(asdict(machine))!=reg['machine_sha256']:raise ValueError('Physical machine changed')
    catalog=full_catalog(machine,reg['shape'],reg['layers'],choice['baseline'])
    if digest([asdict(o) for o in catalog['objects']])!=choice['catalog_sha256']:raise ValueError('Layer catalog changed')
    producer=iter(physical_windows(cohort,machine,catalog,profile,reg['layers'],reg['prefill_microbatch']))
    graph,kernels,meta=next(producer);directory=root/'cases'/case;directory.mkdir(parents=True,exist_ok=False)
    source=RuntimeWindows(directory/'windows',producer,meta);begin=time.monotonic()
    native=VerticalRWDL(machine,request_control=True,refresh=True,gateway_trace_bin_ps=1000000)
    try:
        r=execute_system(machine,graph,native=native,compute_contexts=2,fetch_contexts=2,read_issue_policy='round_robin',
            operand_readiness='contiguous_prefix',weight_cache=WeightCacheConfig(),npu_model=NPUKernelModel(profile,kernels),
            window_source=source,time_advance='boundaries',max_ps=reg['max_ps'],
            activation_sram_read_bytes_per_cycle=machine.rx_write_bytes_per_cycle,
            network_factory=factory(binary=binary,directory=directory/'network',
                ready_router_ids=tuple(r.id for r in machine.routers),ready_slots=16))
    finally:native.close()
    r.update(source_commit=revision(),case=case,registration_sha256=file_sha(root/'registration.json'))
    with gzip.open(directory/'result.json.gz','wt',compresslevel=6) as f:json.dump(r,f)
    write_json(directory/'completion.json',dict(complete=True,case=case,source_commit=revision(),
        makespan_ps=r['makespan_ps'],drained_ps=r['drained_ps'],wall_seconds=time.monotonic()-begin,
        windows=len(source.rows),native_bytes=sum(v['native_bytes'] for v in source.rows),
        result_sha256=file_sha(directory/'result.json.gz'),scope=reg['scope']))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--case')
    p.add_argument('--corpus',type=Path);p.add_argument('--gate-receipts',type=Path,nargs='*',default=())
    p.add_argument('--booksim-binary',type=Path,default=os.getenv('W2W_BOOKSIM_BINARY'));a=p.parse_args()
    if a.prepare:
        if a.corpus is None:p.error('Complete audited corpus required')
        prepare(a.root,a.corpus,a.gate_receipts)
    else:
        if a.booksim_binary is None:p.error('Accepted Native binary required')
        run(a.root,a.case,a.booksim_binary)
