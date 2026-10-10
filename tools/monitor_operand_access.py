#!/usr/bin/env python3
"""Watch a frozen pair, run offline audits once complete, never rerun cases."""
import argparse,json,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path


def monitor(study,source,checks=720):
    reg=json.loads((study/'registration.json').read_text())
    for tick in range(checks):
        rows={}
        for case in reg['cases']:
            path=study/'cases'/case/'completion.json';log=study/'logs'/f'{case}.log'
            lines=log.read_text().splitlines() if log.exists() else []
            if any('Traceback (most recent call last)' in line for line in lines):
                print(json.dumps(dict(failed=case,time_utc=datetime.now(timezone.utc).isoformat(),last=lines[-1:])),flush=True)
                return 1
            if path.exists():
                r=json.loads(path.read_text());rows[case]={k:r[k] for k in ('complete','makespan_ps','source_commit')}
            else:rows[case]=dict(pending=True,last=lines[-1:])
        print(json.dumps(dict(time_utc=datetime.now(timezone.utc).isoformat(),cases=rows)),flush=True)
        if all(r.get('complete') for r in rows.values()):
            return subprocess.run([sys.executable,'-m','w2w.analysis.operand_access','--source',str(study),
                '--output',str(study/'independent-analysis.json')],cwd=source).returncode
        if tick+1<checks:time.sleep(60)
    print('Monitoring limit reached; experiments were not stopped.',flush=True);return 2


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--checks',type=int,default=720);args=p.parse_args()
    if args.checks<1:p.error('Positive check limit required')
    raise SystemExit(monitor(args.study,args.source,args.checks))


if __name__=='__main__':main()
