#!/usr/bin/env python3
"""Monitor registered cases; finalize a conserved zero-reload rejection, never rerun."""
import argparse,hashlib,json,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path


def monitor(study,output,source,checks,interval):
    registration=json.loads((study/'registration.json').read_text());cases=tuple(registration['cases'])
    for tick in range(checks):
        rows={};failed=False
        for case in cases:
            completion=study/'cases'/case/'completion.json';log=study/'logs'/f'{case}.log'
            lines=log.read_text().splitlines() if log.exists() else []
            if (not completion.exists() and lines
                    and lines[-1]=='ValueError: Capacity reload was not observed'):
                p=subprocess.run([sys.executable,'-m','w2w.experiments.run_memory_hierarchy',
                    '--output',str(study),'--finalize-zero-reload',case],cwd=source,
                    stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
                (output/f'{case}-zero-reload-finalization.log').write_text(p.stdout)
                if p.returncode:failed=True
            if completion.exists():
                record=json.loads(completion.read_text())
                rows[case]={k:record[k] for k in ('complete','source_commit','makespan_ps','audit')}
            else:
                rows[case]=dict(pending=True,last_line=lines[-1][:500] if lines else None)
                if any('Traceback (most recent call last)' in line for line in lines):failed=True
        print(json.dumps(dict(time_utc=datetime.now(timezone.utc).isoformat(),cases=rows)),flush=True)
        if failed:
            print('STOP: a case or independent finalization failed; preserve evidence, no rerun.',flush=True)
            return 1
        if all(rows[case].get('complete') for case in cases):
            p=subprocess.run([sys.executable,'-m','w2w.analysis.gateway_hierarchy','--source',str(study),
                '--output',str(output/'hierarchy-analysis.json')],cwd=source,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            (output/'hierarchy-analysis.log').write_text(p.stdout);print(p.stdout,flush=True)
            records={}
            paths=(study/'registration.json',*study.glob('inputs/*'),
                *study.glob('cases/*/completion.json'),*study.glob('cases/*/result.json.gz'))
            for path in paths:
                h=hashlib.sha256()
                with path.open('rb') as f:
                    for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
                records[str(path.relative_to(study))]=dict(bytes=path.stat().st_size,sha256=h.hexdigest())
            (output/'hierarchy-evidence-sha256.json').write_text(json.dumps(
                dict(analysis_exit=p.returncode,files=records),indent=2)+'\n')
            return p.returncode
        if tick+1<checks:time.sleep(interval)
    print('STOP: monitoring limit reached; experiments are not stopped.',flush=True)
    return 2


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--checks',type=int,default=720)
    p.add_argument('--interval',type=int,default=60);args=p.parse_args()
    if args.checks<1 or not 1<=args.interval<=60:p.error('Use positive checks and a 1–60 second interval')
    raise SystemExit(monitor(args.study,args.output,args.source,args.checks,args.interval))

if __name__=='__main__':main()
