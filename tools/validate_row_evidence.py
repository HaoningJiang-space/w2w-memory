"""Actual paid row cycles versus compact epochs under queued resident contexts."""
import argparse,gzip,json,time
from dataclasses import replace
from pathlib import Path

from tools.validate_npu_physical import graph
from w2w.architecture.compiler import compile_machine
from w2w.architecture.npu_profile import reference_profile
from w2w.architecture.presets.recipes import from_recipe
from w2w.backends.booksim.adapter import factory
from w2w.backends.ramulator import VerticalRWDL
from w2w.common.event_archive import canonical_sha
from w2w.common.io import write_json
from w2w.domain.execution import ExecutionGraph
from w2w.provenance import revision
from w2w.system.kernel import execute_system
from w2w.system.row_mapping import RowMappingKernelModel,reprogram_graph
from w2w.system.weight_cache import WeightCacheConfig
from w2w.validation.npu_resources import audit_npu_result
from w2w.validation.request_control import audit_request_control
from w2w.validation.vertical_access import audit_vertical_result
from w2w.workloads.moe_trace import file_sha


def run(output,prerequisite,binary):
    prior=json.loads(prerequisite.read_text())
    if not prior.get('passed'):raise ValueError('Accepted resident row qualification required')
    output.mkdir(parents=True,exist_ok=False);p=reference_profile();machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'))
    start=time.monotonic();proofs=[]
    for kind,N,K in (('gate',128,4096),('up',128,4096),('down',4096,128)):
        tasks=[];objects=[];edges=[];kernels={}
        for index in range(3):
            g,ks=graph(machine,1,N,K,p,f'same/{index}');obj=f'W{index}'
            objects.append(replace(g.objects[0],id=obj,offset_bytes=index*1048576));edges.extend(g.data)
            tasks.extend(replace(t,reads=tuple(replace(r,object_id=obj) for r in t.reads),
                stream=replace(t.stream,weight_object=obj) if t.stream else None) for t in g.tasks)
            kernels.update({k:replace(v,weight_object=obj) for k,v in ks.items()})
        g=reprogram_graph(ExecutionGraph(tasks,objects,edges),kernels,p,'row_auto')
        rows=[];reference=None;config_reference=None;topology_reference=None
        for evidence in ('epochs','cycles'):
            directory=output/f'{kind}-{evidence}';directory.mkdir()
            model=RowMappingKernelModel(p,kernels,policy='row_auto',evidence=evidence)
            cache=WeightCacheConfig(initial_resident=tuple((g.tasks[-1].tile,o.id) for o in objects))
            native=VerticalRWDL(machine,request_control=True,refresh=True,gateway_trace_bin_ps=1000000)
            try:
                r=execute_system(machine,g,native=native,network_factory=factory(binary=binary,directory=directory/'network',
                    ready_router_ids=tuple(v.id for v in machine.routers),ready_slots=16),max_ps=2000000000,time_advance='boundaries',
                    compute_contexts=2,fetch_contexts=2,read_issue_policy='round_robin',weight_cache=cache,
                    operand_readiness='contiguous_prefix',activation_sram_read_bytes_per_cycle=machine.rx_write_bytes_per_cycle,npu_model=model)
            finally:native.close()
            path=directory/'result.json.gz'
            with gzip.open(path,'wt') as f:json.dump(r,f)
            a=audit_vertical_result(r);audit_request_control(r);n=audit_npu_result(r)
            if a['native_bytes'] or max(r['compute_execution']['context_peak'].values())!=2:
                raise ValueError('Resident queued-context condition was not exercised')
            # Only the evidence representation and archive configuration hash
            # differ. Every other resource, physical event and ps time agrees.
            comparable=json.loads(json.dumps(r));comparable['events']=[e for e in comparable['events'] if e['kind'] not in ('npu_cycle','npu_epoch')]
            comparable['npu_execution'].pop('evidence');comparable['network']['identity'].pop('config_sha256');comparable.pop('input_sha256')
            config=(directory/'network/network.conf').read_text().replace(str((directory/'network').resolve()),'<ARCHIVE>')
            topology=(directory/'network/network.anynet').read_bytes()
            if reference is None:reference=comparable;config_reference=config;topology_reference=topology
            elif comparable!=reference or config!=config_reference or topology!=topology_reference:
                raise ValueError('Compact row epoch changed complete physical events/resources/output under queued contexts')
            rows.append(dict(evidence=evidence,makespan_ps=r['makespan_ps'],physical_audit=a,npu_audit=n,
                file=str(path.relative_to(output)),sha256=file_sha(path),comparison_sha256=canonical_sha(comparable)))
        proofs.append(dict(kind=kind,passed=True,rows=rows))
    write_json(output/'receipt.json',dict(passed=True,analysis_source=revision(),P2A_receipt_sha256=file_sha(prerequisite),proofs=proofs,
        wall_seconds=time.monotonic()-start,scope='Six actual resident physical executions: three matrices compete for two contexts in one cluster, for Gate/Up/Down. All array cycles/scale routing/shared ports and queued owners independently audited; compact epochs preserve every non-array physical event/resource/output time. No change to ongoing frozen P3 jobs or original B1 evidence.'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('output','prerequisite','booksim-binary'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.output,a.prerequisite,a.booksim_binary)
