"""Exact Native/carry/event qualification of a host-only candidate index."""
import gzip,json,time
from dataclasses import asdict,replace
from pathlib import Path

from w2w.backends.booksim.adapter import factory
from w2w.backends.ramulator import VerticalRWDL
from w2w.common.event_archive import read_execution,canonical_sha
from w2w.common.io import write_json
from w2w.domain.execution import ExecutionGraph
from w2w.provenance import revision
from w2w.system.kernel import execute_system
from w2w.system.runtime_windows import RuntimeWindows
from w2w.system.weight_cache import WeightCacheConfig
from w2w.analysis.runtime_windows import audit_window_chain
from w2w.workloads.moe_trace import file_sha


def fixture(machine,p,tag,policy):
    from tools.validate_operand_streaming import inputs
    from w2w.system.operand_streaming import StreamingKernelModel
    from w2w.system.row_mapping import RowMappingKernelModel
    tasks=[];objects=[];edges=[];kernels={}
    for index in range(3):
        graph,ks,_=inputs(machine,p,128,4096,f'{tag}/{index}',policy)
        name=f'W{index}';obj=replace(graph.objects[0],id=name,offset_bytes=index*1048576)
        objects.append(obj);edges.extend(graph.data)
        for task in graph.tasks:
            tasks.append(replace(task,reads=tuple(replace(r,object_id=name) for r in task.reads),
                stream=replace(task.stream,weight_object=name) if task.stream else None))
        kernels.update({k:replace(v,weight_object=name) for k,v in ks.items()})
    model=StreamingKernelModel(p,kernels) if policy=='streaming_os' else RowMappingKernelModel(p,kernels,policy=policy)
    return ExecutionGraph(tuple(tasks),tuple(objects),tuple(edges)),kernels,model


def qualify(root,machine,p,binary):
    root.mkdir(parents=True,exist_ok=False);start=time.monotonic();comparisons=[]
    for policy in ('best_os','streaming_os'):
        reference=None;reference_config=None;reference_topology=None;rows=[]
        for indexed in (False,True):
            directory=root/f'{policy}-{int(indexed)}';directory.mkdir()
            graph,kernels,model=fixture(machine,p,'cold',policy)
            second,k2,_=fixture(machine,p,'warm',policy)
            metadata=lambda ks:dict(npu_kernels={k:asdict(v) for k,v in ks.items()})
            source=RuntimeWindows(directory/'windows',iter(((second,k2,metadata(k2)),)),metadata(kernels))
            native=VerticalRWDL(machine,request_control=True,refresh=True,gateway_trace_bin_ps=1000000)
            begin=time.monotonic()
            try:
                result=execute_system(machine,graph,native=native,network_factory=factory(binary=binary,directory=directory/'network',
                    ready_router_ids=tuple(r.id for r in machine.routers),ready_slots=16),max_ps=2000000000,time_advance='boundaries',
                    compute_contexts=2,fetch_contexts=2,read_issue_policy='round_robin',weight_cache=WeightCacheConfig(),
                    operand_readiness='contiguous_prefix',activation_sram_read_bytes_per_cycle=machine.rx_write_bytes_per_cycle,
                    npu_model=model,window_source=source,indexed_admission=indexed)
            finally:native.close()
            proof=audit_window_chain(result,directory/'windows')
            if proof['windows']!=2 or source.rows[1]['native_bytes'] or source.rows[0]['native_bytes']!=3*524416:
                raise ValueError('Host index gate lost cold/warm independent matrix identities')
            normalized=[]
            for window in source.rows:
                raw=read_execution(directory/'windows'/window['file'])
                # Archive-directory identity is the only physical-record field
                # normalized. The actual configuration/topology must match.
                raw['network']['identity'].pop('config_sha256')
                normalized.append(raw)
            if max(normalized[0]['fetch_execution']['peak_contexts'].values())!=2:
                raise ValueError('Host index gate did not exercise finite fetch admission')
            comparable=dict(windows=normalized,cleanup_events=result['cleanup_events'],
                makespan_ps=result['makespan_ps'],drained_ps=result['drained_ps'],quantum_ps=result['quantum_ps'])
            config=(directory/'network/network.conf').read_text().replace(str((directory/'network').resolve()),'<ARCHIVE>')
            topology=(directory/'network/network.anynet').read_bytes()
            if reference is None:reference=comparable;reference_config=config;reference_topology=topology
            elif comparable!=reference or config!=reference_config or topology!=reference_topology:
                raise ValueError('Host candidate index changed a complete Native/NoC/SRAM/cache/array event or carry state')
            path=directory/'result.json.gz'
            with gzip.open(path,'wt') as f:json.dump(result,f)
            rows.append(dict(indexed_admission=indexed,result_sha256=file_sha(path),file=str(path.relative_to(root)),
                canonical_comparison_sha256=canonical_sha(comparable),proof=proof,wall_seconds=time.monotonic()-begin))
        comparisons.append(dict(policy=policy,passed=True,rows=rows))
    value=dict(passed=True,source_commit=revision(),comparisons=comparisons,wall_seconds=time.monotonic()-start,
        scope='Host-only candidate indexing: two policies, three independent cold matrices sharing one cluster/two fetch contexts, then three warm matrices across the real drain boundary. All decoded physical events, resources, carry states, output times, configuration and topology identical; only archive-path config identity normalized. No hardware or scheduling change.')
    write_json(root/'receipt.json',value);return value
