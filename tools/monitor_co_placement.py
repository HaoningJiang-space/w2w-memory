#!/usr/bin/env python3
"""Frozen three-case cold gate followed by the registered finite-cache pair."""
import argparse,json,os,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from w2w.common.io import write_json
from w2w.provenance import revision


def campaign(root,binary,cold_baseline,warm_baseline):
    source=Path(__file__).resolve().parents[1]
    for mode in ('cold','multilayer'):
        reg=json.loads((root/mode/'registration.json').read_text())
        if reg['source_commit']!=revision():raise ValueError('Controller source differs from registered worker source')
    for mode,baseline in (('cold',cold_baseline),('multilayer',warm_baseline)):
        reg=json.loads((root/mode/'registration.json').read_text());workers={};pids={};started=datetime.now(timezone.utc).isoformat()
        for case in reg['cases']:
            cmd=[sys.executable,'-m','w2w.experiments.run_co_placement','--output',str(root/mode),'--case',case,'--booksim-binary',str(binary)]
            with (root/'logs'/f'{mode}-{case}.log').open('xb') as f:
                p=subprocess.Popen(cmd,cwd=source,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
            workers[case]=p;pids[case]=dict(pid=p.pid,command=cmd)
        write_json(root/f'{mode}-launch.json',dict(source_commit=revision(),started_utc=started,workers=pids,
            contract='Fixed registered cases, no automatic retry; next workload starts after complete independent cold audit, not performance selection.'))
        while any(p.poll() is None for p in workers.values()):
            print(json.dumps(dict(time_utc=datetime.now(timezone.utc).isoformat(),mode=mode,status={k:p.poll() for k,p in workers.items()})),flush=True)
            time.sleep(30)
        if any(p.returncode for p in workers.values()):raise RuntimeError('Registered worker failed; preserve logs and stop the next gate')
        cmd=[sys.executable,'-m','w2w.analysis.co_placement','--source',str(root/mode),'--output',str(root/mode/'analysis.json'),'--baseline',str(baseline)]
        with (root/'logs'/f'{mode}-readback.log').open('xb') as f:subprocess.run(cmd,cwd=source,stdout=f,stderr=subprocess.STDOUT,check=True)
        print(json.dumps(dict(mode=mode,independent_passed=True)),flush=True)
    print(json.dumps(dict(complete=True,independent_passed=True)),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--booksim-binary',type=Path,required=True);p.add_argument('--cold-baseline',type=Path,required=True)
    p.add_argument('--warm-baseline',type=Path,required=True);a=p.parse_args()
    campaign(a.root,a.booksim_binary,a.cold_baseline,a.warm_baseline)


if __name__=='__main__':main()
