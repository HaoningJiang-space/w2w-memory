"""Real-cohort compiler capacity preflight, not application performance."""
import argparse,json,time
from pathlib import Path
from collections import Counter
from w2w.workloads.patterns_adapter import load_corpus
from w2w.experiments.run_real_moe import select_cohort,paired_batches
from w2w.architecture.presets.recipes import from_recipe
from w2w.architecture.compiler import compile_machine
from w2w.architecture.npu_profile import reference_profile
from w2w.mapping.moe_batch_lowering import BASELINES,full_catalog,lower_batch
from w2w.system.builder import SystemBuilder
from w2w.system.npu_kernel import NPUKernelModel
from w2w.system.weight_cache import WeightCacheConfig
from w2w.domain.execution import ExecutionGraph,DataEdge,ControlEdge
from w2w.common.io import write_json
from w2w.workloads.moe_trace import file_sha
from w2w.provenance import revision


def run(corpus):
    begin=time.monotonic();captures=tuple(load_corpus(corpus));m=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'))
    p=reference_profile();cache=WeightCacheConfig();budget=8*1024**2-cache.metadata_bytes_per_cluster-136-64
    rows=[]
    for B in (1,4,16,32):
        cohort=select_cohort(captures,B);batches=list(paired_batches(cohort,('0','1'),32))
        decode=[bs for bs in batches if bs[0].observations[0].phase=='decode']
        # Worst actual M is selected only for compiler qualification, never for
        # architecture timing; the application still executes every window.
        worst=max(decode,key=lambda bs:max(len(ts) for b in bs for e,ts in b.expert_to_tokens))
        for baseline in BASELINES:
            catalog=full_catalog(m,captures[0]['shape'],('0','1'),baseline)
            for view,bs in (('first-prefill',batches[0]),('largest-decode-M',worst)):
                tasks=[];data=[];control=[];kernels={};aux={};previous=[]
                for batch in bs:
                    prefix=f'L{batch.layer_id}/';g,k,meta=lower_batch(batch,m,catalog,p,prefix=prefix)
                    inputs=[prefix+f't{t}/input' for t in range(batch.token_count)]
                    for a,b in zip(previous,inputs):data.append(DataEdge(prefix+a+'/layer-input',a,b,8192))
                    for a in previous:
                        for b in inputs:control.append(ControlEdge(a,b))
                    tasks.extend(g.tasks);data.extend(g.data);control.extend(g.control);kernels.update(k);aux.update(meta['auxiliary']);previous=meta['finish_tasks']
                graph=ExecutionGraph(tuple(tasks),catalog['objects'],tuple(data),tuple(control))
                builder=SystemBuilder(m).validate_graph(graph);NPUKernelModel(p,kernels,auxiliary=aux).validate(m,graph)
                work={t.id:builder.footprint[t.id]-(sum(r.size_bytes for r in t.reads) if t.id in kernels else 0) for t in tasks}
                if max(work.values())>budget:raise ValueError('Actual grouped task cannot fit finite non-cache SRAM; explicitly tile, never add capacity')
                rows.append(dict(B=B,baseline=baseline,view=view,phase=bs[0].observations[0].phase,decode_step=bs[0].observations[0].decode_step,
                    actual_tokens=bs[0].token_count,largest_expert_M=max(len(ts) for b in bs for e,ts in b.expert_to_tokens),
                    largest_task=max(work,key=work.get),largest_task_noncache_bytes=max(work.values()),task_noncache_budget_bytes=budget,
                    requests=[r.request_id for r in bs[0].observations],tokens=[r.token_id for r in bs[0].observations],tasks=len(tasks)))
    return dict(passed=True,source_commit=revision(),corpus_manifest_sha256=file_sha(corpus/'manifest.json'),cases=rows,wall_seconds=time.monotonic()-begin,
        scope='Real source-order nested cohorts, full H/I, full independent two-layer catalogs; first prefill and largest actual decode-M compiler views. All 24 views close intrinsic task and port budgets. This is a necessary capacity check, not proof of dynamic peak/deadlock freedom or complete captured-request performance; those require the full physical campaign.')


if __name__=='__main__':
    q=argparse.ArgumentParser(description=__doc__);q.add_argument('--corpus',type=Path,required=True);q.add_argument('--output',type=Path,required=True);a=q.parse_args()
    if a.output.exists():raise ValueError('Retain earlier compiler qualification')
    write_json(a.output,run(a.corpus))
