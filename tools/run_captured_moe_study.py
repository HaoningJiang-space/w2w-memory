"""Serial background controller: registered full-phase cases, no retries."""
import argparse,json,subprocess,sys,time
from pathlib import Path
from w2w.common.io import write_json
from w2w.provenance import revision


def run(root,binary):
    reg=json.loads((root/'registration.json').read_text())
    if revision()!=reg['source_commit']:raise ValueError('Controller must use frozen execution source')
    (root/'controller-lock').mkdir(exist_ok=False);(root/'logs').mkdir(exist_ok=False)
    for case in reg['cases']:
        command=[sys.executable,'-m','w2w.experiments.run_captured_moe','--output',str(root),
            '--case',case,'--booksim-binary',str(binary)]
        with (root/'logs'/f'{case}.log').open('w') as f:
            p=subprocess.Popen(command,stdout=f,stderr=subprocess.STDOUT);started=time.monotonic()
            while p.poll() is None:
                write_json(root/'controller-status.json',dict(state='running',case=case,worker_pid=p.pid,
                    elapsed_wall_seconds=time.monotonic()-started,source_commit=reg['source_commit']))
                time.sleep(30)
        if p.returncode:
            write_json(root/'controller-status.json',dict(state='failed',case=case,exit_code=p.returncode,
                contract='No automatic retry; retain failure and earlier completed cases.'))
            raise SystemExit(p.returncode)
    with (root/'logs/independent-readback.log').open('w') as f:
        p=subprocess.run([sys.executable,'-m','w2w.analysis.captured_moe','--root',str(root),
            '--output',str(root/'independent-readback.json')],stdout=f,stderr=subprocess.STDOUT)
    write_json(root/'controller-status.json',dict(state='complete' if p.returncode==0 else 'readback_failed',
        source_commit=reg['source_commit'],exit_code=p.returncode))
    raise SystemExit(p.returncode)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--booksim-binary',type=Path,required=True);a=p.parse_args();run(a.root,a.booksim_binary)
