#!/usr/bin/env python3
"""Check registered background processes once/minute; audit and analyze, without retries."""
import argparse,datetime,json,subprocess,sys,time
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','launch','source','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--wait-audit',type=Path)
    p.add_argument('--equivalence-baseline',type=Path);p.add_argument('--equivalence-case')
    a=p.parse_args();jobs=json.loads(a.launch.read_text())['pids'];a.output.mkdir(exist_ok=False)
    while True:
        status={}
        for case,pid in jobs.items():
            completed=a.study/'cases'/case/'completion.json'
            if completed.exists():status[case]='complete';continue
            proc=Path(f'/proc/{pid}/stat')
            if not proc.exists() or proc.read_text().split(') ',1)[1].split()[0]=='Z':
                raise RuntimeError(f'{case} exited without completion; inspect its log; no automatic retry')
            status[case]='running'
        print(json.dumps(dict(time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),status=status)),flush=True)
        if all(s=='complete' for s in status.values()) and (a.wait_audit is None or a.wait_audit.exists()):break
        time.sleep(60)
    def run(argv):subprocess.run([sys.executable,*map(str,argv)],cwd=a.source,check=True)
    audit=a.output/'placement-analysis.json'
    run(['-m','w2w.analysis.static_placement','--source',a.study,'--output',audit])
    run(['-m','w2w.analysis.ffn_stages','--source',a.study,'--audited',audit,'--output',a.output/'stages.json'])
    if a.equivalence_baseline:
        if not a.equivalence_case:raise ValueError('Equivalence candidate case required')
        run([a.source/'tools/check_simulator_equivalence.py','--baseline',a.equivalence_baseline,
            '--candidate',a.study/'cases'/a.equivalence_case,'--output',a.output/'migration-proof.json'])
    print('Completed independent placement/stage audit; no result-dependent retries',flush=True)


if __name__=='__main__':main()
