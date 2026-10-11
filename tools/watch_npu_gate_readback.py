"""Read a frozen live campaign after completion; never restart or mutate physics."""
import argparse,json,time
from pathlib import Path
from tools.audit_full_llm_serving import run as audit_serving
from tools.analyze_npu_gates import render
from w2w.common.io import write_json
from w2w.provenance import revision


def identity(pid,campaign):
    path=Path('/proc')/str(pid)
    try:
        if path.joinpath('stat').read_text().split(') ',1)[1][0]=='Z':return None
        command=path.joinpath('cmdline').read_bytes().split(b'\0')
    except FileNotFoundError:return None
    if str(campaign).encode() not in command:raise RuntimeError('Campaign PID now belongs to another command')
    return command


def observe(path):
    # Status writes are observations, not execution. A partial write during a
    # live poll is unknown; it is never a reason to restart the physical job.
    try:return json.loads(path.read_text())
    except (FileNotFoundError,json.JSONDecodeError):return {}


def run(campaign,pid,evidence,reference,output):
    campaign=campaign.resolve();initial=identity(pid,campaign)
    if initial is None:raise RuntimeError('Specific campaign controller is not live; no watcher relaunch')
    output.mkdir(parents=True,exist_ok=False);readback=output/'serving-readback.json';g3=campaign/'real-moe';g4=campaign/'full-llm-B1'
    write_json(output/'launch.json',dict(controller_pid=pid,command=[v.decode() for v in initial if v],analysis_source=revision(),campaign=str(campaign)))
    try:
        while True:
            status=observe(campaign/'status.json')
            if (status.get('state') in ('failed','storage_blocked') or status.get('G4_error')):
                raise RuntimeError('Frozen campaign ended or rejected a prerequisite; no automatic retry')
            if observe(g4/'controller-status.json').get('state')=='complete' and not readback.exists():audit_serving(g4,readback)
            complete=observe(g3/'controller-status.json').get('state')=='complete'
            if complete and readback.exists():
                render(evidence,output/'final-analysis',study=g3,serving=g4,final=True,npu_reference=reference,serving_readback=readback)
                decision=json.loads((output/'final-analysis/decision.json').read_text())
                write_json(output/'status.json',dict(state='architecture_accepted' if decision.get('architecture_gate_passed') is True else 'mapping_screen_complete_architecture_unproven',
                    source_commit=revision(),baseline_screen_passed=decision['baseline_screen_passed'],architecture_gate_passed=decision['architecture_gate_passed']))
                return
            if identity(pid,campaign)!=initial:raise RuntimeError('Specific campaign controller ended before completed evidence; no automatic retry')
            write_json(output/'status.json',dict(state='verified_wait',controller_pid=pid,full_serving_readback=readback.exists(),complete_G3=complete,source_commit=revision()))
            time.sleep(30)
    except Exception as error:
        write_json(output/'status.json',dict(state='failed',reason=str(error),source_commit=revision(),no_automatic_retry=True));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('campaign','evidence','npu-reference','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--controller-pid',type=int,required=True);a=p.parse_args()
    run(a.campaign,a.controller_pid,a.evidence,a.npu_reference,a.output)
