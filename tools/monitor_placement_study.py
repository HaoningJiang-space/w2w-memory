#!/usr/bin/env python3
"""Complete frozen performance gates, cold placement, then the selected 24-token pair.

Poll once/minute; stop on a failed process or audit. No automatic retry and no
selection from the multilayer trace. Run in an isolated remote study directory.
"""
import argparse,datetime,hashlib,json,os,subprocess,sys,time
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--analysis-source',type=Path,required=True);p.add_argument('--booksim-binary',type=Path,required=True)
    a=p.parse_args();r=a.root;python=sys.executable;env=os.environ.copy();env['W2W_BOOKSIM_BINARY']=str(a.booksim_binary)
    def run(argv,source=a.source):subprocess.run([python,*map(str,argv)],cwd=source,env=env,check=True)
    proofs={}
    for case in ('central-plus','distributed'):
        proof=r/f'gate-r3-full-{case}-proof.json'
        run([a.source/'tools/check_simulator_equivalence.py','--baseline',r/f'gate-full-{case}-baseline',
             '--candidate',r/f'gate-r3-full-{case}','--output',proof])
        old=json.loads((r/f'gate-full-{case}-baseline/completion.json').read_text())
        new=json.loads((r/f'gate-r3-full-{case}/completion.json').read_text())
        proofs[case]=dict(json.loads(proof.read_text()),baseline=old,candidate=new,
            total_wall_speedup=old['total_wall_seconds']/new['total_wall_seconds'])
        if proofs[case]['total_wall_speedup']<2:raise RuntimeError('Wall-clock engineering target not met')
    (r/'p1-analysis.json').write_text(json.dumps(dict(passed=True,cases=proofs,
        measurement='same frozen cold graph, command recorder and endpoint hashing; total includes command audit and JSON/gzip; concurrent same-host runs, single measurement'),indent=2))
    def launch(study,policies,mode):
        processes={};jobs={}
        for policy in policies:
            with (r/'logs'/f'placement-{mode}-{policy}.log').open('xb') as log:
                child=subprocess.Popen([python,'-m','w2w.experiments.run_static_placement','--output',str(study),
                    '--case',policy,'--booksim-binary',str(a.booksim_binary)],cwd=a.source,env=env,
                    stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                processes[policy]=child;jobs[policy]=child.pid
        record=dict(pids=jobs,source=str(a.source),interval_seconds=60,
            time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        if mode=='multilayer':record['cold_analysis_sha256']=hashlib.sha256((r/'placement-cold-analysis.json').read_bytes()).hexdigest()
        (r/f'launch-placement-{mode}.json').write_text(json.dumps(record,indent=2))
        while any(child.poll() is None for child in processes.values()):
            print(json.dumps(dict(mode=mode,status={k:child.poll() for k,child in processes.items()},
                time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())),flush=True)
            time.sleep(60)
        if any(child.returncode for child in processes.values()):raise RuntimeError('Placement execution failed; no automatic retry')
    cold=r/'placement-cold-r3'
    launch(cold,('reference','balanced','hybrid'),'cold')
    run(['-m','w2w.analysis.static_placement','--source',cold,'--output',r/'placement-cold-analysis.json'],a.analysis_source)
    evidence=json.loads((r/'placement-cold-analysis.json').read_text());selected=evidence['selected_nonreference']
    # A slower alternative is still a valid negative result and is confirmed.
    multi=r/'placement-multilayer-r1'
    run(['-m','w2w.experiments.run_static_placement','--prepare','--mode','multilayer','--policies',
         'reference',selected,'--output',multi])
    launch(multi,('reference',selected),'multilayer')
    run(['-m','w2w.analysis.static_placement','--source',multi,'--output',r/'placement-multilayer-analysis.json'],a.analysis_source)
    print('P0-P4 complete: both placement studies independently audited',flush=True)


if __name__=='__main__':main()
