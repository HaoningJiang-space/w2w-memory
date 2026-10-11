"""Frozen complete-cohort background controller; no retries, truncation or silent fallback."""
import argparse,json,os,shutil,subprocess,sys,time
from pathlib import Path
from w2w.analysis.real_moe import analyze_case
from w2w.common.io import write_json
from w2w.workloads.moe_trace import file_sha


def run(root,binary,case_order):
    reg=json.loads((root/'registration.json').read_text());status=root/'controller-status.json'
    command_receipts={k:file_sha(v) for k,v in dict(booksim=binary,ramulator=os.environ['W2W_RAMULATOR_BRIDGE']).items()}
    receipts={};start=time.monotonic()
    for case in case_order:
        if case not in reg['cases'] or (root/'cases'/case).exists():raise ValueError('Case unknown or previously attempted; explicit new registration required')
        # Preserve other users/experiments. Stop before starting another full case
        # if retained evidence would crowd the shared filesystem.
        free=shutil.disk_usage(root).free
        if free<60*1024**3:
            write_json(status,dict(state='storage_blocked',next_case=case,free_bytes=free,completed=receipts));return 2
        log=(root/f'{case}.log').open('w')
        proc=subprocess.Popen([sys.executable,'-m','w2w.experiments.run_real_moe','--root',str(root),
            '--case',case,'--booksim-binary',str(binary)],stdout=log,stderr=subprocess.STDOUT)
        while proc.poll() is None:
            write_json(status,dict(state='running',case=case,worker_pid=proc.pid,source_commit=reg['source_commit'],
                elapsed_wall_seconds=time.monotonic()-start,completed=receipts,native_sha256=command_receipts,
                contract='One case at a time, all captured prefill and all 128 decode steps. No automatic retry.'))
            time.sleep(10)
        log.close()
        if proc.returncode:
            write_json(status,dict(state='failed',case=case,returncode=proc.returncode,completed=receipts));return proc.returncode
        receipt=analyze_case(root,case);write_json(root/'cases'/case/'analysis.json',receipt)
        receipts[case]=dict(passed=True,analysis_sha256=file_sha(root/'cases'/case/'analysis.json'),
            makespan_ps=receipt['proof']['makespan_ps'],native_bytes=receipt['proof']['native_bytes'])
    write_json(status,dict(state='complete',passed=True,completed=receipts,wall_seconds=time.monotonic()-start,native_sha256=command_receipts));return 0


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--booksim-binary',type=Path,required=True);p.add_argument('--cases',nargs='+');a=p.parse_args()
    reg=json.loads((a.root/'registration.json').read_text())
    raise SystemExit(run(a.root,a.booksim_binary,a.cases or list(reg['cases'])))
