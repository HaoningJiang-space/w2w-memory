#!/usr/bin/env python3
"""Frozen S0/S1 cold matrix, two concurrent cases at a time, then independent audits."""
import argparse,datetime,json,os,subprocess,sys,time
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('root','source','booksim-binary','old-reference'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();r=a.root;r.mkdir(exist_ok=False);(r/'logs').mkdir();env=os.environ.copy();env['W2W_BOOKSIM_BINARY']=str(a.booksim_binary)
    def run(argv):subprocess.run([sys.executable,*map(str,argv)],cwd=a.source,env=env,check=True)
    for execution,policies in (('s0',('reference','phase-split')),('s1',('reference','hybrid','balanced','phase-split'))):
        study=r/execution
        run(['-m','w2w.experiments.run_static_placement','--prepare','--execution',execution,'--mode','cold','--policies',*policies,'--output',study])
    for execution,batch in (('s1',('reference','phase-split')),('s0',('reference','phase-split')),('s1',('hybrid','balanced'))):
        processes={}
        for policy in batch:
            with (r/'logs'/f'{execution}-{policy}.log').open('xb') as log:
                processes[policy]=subprocess.Popen([sys.executable,'-m','w2w.experiments.run_static_placement','--output',str(r/execution),
                    '--case',policy,'--booksim-binary',str(a.booksim_binary)],cwd=a.source,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        (r/f'launch-{execution}-{batch[0]}.json').write_text(json.dumps(dict(pids={k:v.pid for k,v in processes.items()},
            execution=execution,time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2))
        while any(child.poll() is None for child in processes.values()):
            print(json.dumps(dict(time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),execution=execution,
                status={k:v.poll() for k,v in processes.items()})),flush=True);time.sleep(60)
        if any(child.returncode for child in processes.values()):raise RuntimeError('Execution failed; no automatic retry')
    for execution in ('s0','s1'):
        audit=r/f'{execution}-analysis.json'
        run(['-m','w2w.analysis.static_placement','--source',r/execution,'--output',audit])
        run(['-m','w2w.analysis.ffn_stages','--source',r/execution,'--audited',audit,'--output',r/f'{execution}-stages.json'])
    run([a.source/'tools/check_simulator_equivalence.py','--baseline',a.old_reference,'--candidate',r/'s0/cases/reference',
        '--output',r/'s0-reference-migration.json'])
    print('S0/S1 cold placement matrix and migration gate independently complete',flush=True)


if __name__=='__main__':main()
