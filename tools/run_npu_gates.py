"""One-shot complete G3/G4 campaign after separately accepted resource gates.

No automatic experiment retries. Qualification captures are never counted as
complete request/model evidence. Only completed audited campaigns release G5.
"""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
from w2w.common.io import write_json
from w2w.workloads.moe_trace import file_sha
from w2w.provenance import revision
from w2w.experiments.run_real_moe import prepare as prepare_moe
from w2w.experiments.run_full_llm import prepare as prepare_llm


def alive(pid):
    path=Path('/proc')/str(pid)/'stat'
    return path.exists() and path.read_text().split(') ',1)[1][0]!='Z'


def run(root,evidence,corpus,config,binary,resource,context,resource_pid,context_pid,existing_moe_study=None):
    root.mkdir(parents=True,exist_ok=False);jobs={};logs=[];launched=[];g3=existing_moe_study or root/'real-moe';g4=root/'full-llm-B1';source=revision();g4_error=None
    base=[evidence/'npu-reference-r2.json',evidence/'compute-r4/receipt.json',evidence/'stream-r4/receipt.json',
        evidence/'boundary-r8/receipt.json',evidence/'bf16-boundary-r8/receipt.json',evidence/'equivalence-r10b/receipt.json']
    serving_gates=[evidence/'gqa-reference-r10b.json',evidence/'idle-boundary-r13/receipt.json']
    def ready(path,pid=None):
        if path.exists():
            if json.loads(path.read_text()).get('passed') is not True:raise ValueError(f'Failed prerequisite: {path}')
            return True
        if pid and not alive(pid):raise RuntimeError(f'Qualification ended without acceptance: {path}')
        return False
    def launch(name,args):
        log=(root/(name+'.log')).open('xb');logs.append(log)
        process=subprocess.Popen([sys.executable,*args],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        jobs[name]=process;launched.append(dict(name=name,pid=process.pid,args=args,source_commit=source))
        write_json(root/'launches.json',launched)
    try:
        while True:
            for name,process in jobs.items():
                if process.poll() not in (None,0):
                    if name=='G4':g4_error=f'G4 failed ({process.returncode}); no automatic retry'
                    else:raise RuntimeError(f'{name} failed ({process.returncode}); no automatic retry')
            for path in base:ready(path)
            resource_ready=ready(resource,resource_pid)
            try:context_ready=ready(context,context_pid)
            except (RuntimeError,ValueError) as error:context_ready=False;g4_error=str(error)
            if resource_ready and all(p.exists() for p in base) and 'G3' not in jobs and existing_moe_study is None:
                # Re-read archived qualification under the current independent
                # auditor before accepting an earlier execution-source receipt.
                import gzip
                from w2w.analysis.runtime_windows import audit_window_chain
                from w2w.analysis.service_bounds import service_bounds
                r=json.load(gzip.open(resource.parent/'result.json.gz','rt'))
                proof=audit_window_chain(r,resource.parent/'windows',visit=lambda raw,row:service_bounds(raw))
                write_json(root/'resource-readback.json',dict(passed=True,source_commit=source,proof=proof,receipt_sha256=file_sha(resource)))
                prepare_moe(g3,corpus,[*base,resource,root/'resource-readback.json'])
                launch('G3',['-m','tools.run_real_moe_study','--root',str(g3),'--booksim-binary',str(binary)])
            prerequisite=g3/'cases/B1-up_local/analysis.json'
            if context_ready and prerequisite.exists() and all(ready(path) for path in serving_gates) and 'G4' not in jobs and g4_error is None:
                ready(prerequisite);ready(context)
                prepare_llm(g4,corpus,config,1,[*base,*serving_gates,resource,context,prerequisite])
                launch('G4',['-m','w2w.experiments.run_full_llm','--root',str(g4),'--coordinate','--booksim-binary',str(binary)])
            status=dict(source_commit=source,state='running',resource_qualification=resource_ready,context_qualification=context_ready,
                G1='accepted full corpus analysis',G2='accepted shape/core/physical microkernels',
                G3='complete' if (g3/'controller-status.json').exists() and json.loads((g3/'controller-status.json').read_text()).get('state')=='complete' else ('running' if 'G3' in jobs or existing_moe_study else 'awaiting resource gate'),
                G4='failed (G3 continues)' if g4_error else ('complete' if (g4/'serving-results.json').exists() else ('running' if 'G4' in jobs else 'awaiting context and complete B1 Up-local')),G5='awaiting complete G3/G4 evidence',
                G4_error=g4_error,G3_study=str(g3),
                processes=[dict(name=n,pid=p.pid,returncode=p.poll()) for n,p in jobs.items()])
            write_json(root/'status.json',status)
            if existing_moe_study and (g3/'controller-status.json').exists() and json.loads((g3/'controller-status.json').read_text()).get('state') in ('failed','storage_blocked'):
                raise RuntimeError('External G3 controller stopped; accepted completed cases are preserved')
            if status['G3']=='complete' and g4_error:raise RuntimeError(g4_error)
            if status['G3']=='complete' and status['G4']=='complete' and 'G5' not in jobs:
                launch('G5',['tools/analyze_npu_gates.py','--evidence',str(evidence),'--output',str(root/'final-analysis'),
                    '--study',str(g3),'--serving',str(g4),'--final'])
            if 'G5' in jobs and jobs['G5'].poll()==0:
                ready(root/'final-analysis/decision.json');status.update(state='complete',G5='complete evidence-based decision');write_json(root/'status.json',status);return
            time.sleep(10)
    except Exception as error:
        write_json(root/'status.json',dict(state='failed',source_commit=source,reason=str(error),no_automatic_retry=True,launched=launched))
        # Only processes created by this controller, never historical work.
        for process in jobs.values():
            if process.poll() is None:os.killpg(process.pid,15)
        raise
    finally:
        for log in logs:log.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','evidence','corpus','config','booksim-binary','resource','context'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--resource-pid',type=int,required=True);p.add_argument('--context-pid',type=int,required=True)
    p.add_argument('--existing-moe-study',type=Path);a=p.parse_args()
    run(a.root,a.evidence,a.corpus,a.config,a.booksim_binary,a.resource,a.context,a.resource_pid,a.context_pid,getattr(a,'existing_moe_study',None))
