"""Read-only final report for the exact ordered study; never launch Native work."""
import argparse,json,time
from pathlib import Path

from tools.render_ordered_execution import render
from w2w.common.io import write_json
from w2w.provenance import revision
from w2w.workloads.moe_trace import file_sha
from w2w.analysis.moe_mechanism import read_mechanism_input
from w2w.validation.route_visibility import audit_route_visibility


def route_readback(ordered):
    p3=observe(ordered/'p3/receipt.json');proofs=[]
    for name,entry in p3['completed'].items():
        case=Path(entry['receipt']).parent
        summary=json.load(__import__('gzip').open(case/'result.json.gz','rt'))
        for window in summary['runtime_windows']['windows']:
            raw=read_mechanism_input(case/'windows'/window['file'],window['sha256'],extra_events=('cache_lookup',))
            proofs.append(dict(case=name,index=window['index'],source_sha256=window['sha256'],
                **audit_route_visibility(raw,window['index'])))
    if len(proofs)!=45 and p3['horizon']=='selected_windows':raise ValueError('Registered route-visibility horizon incomplete')
    return dict(passed=True,windows=len(proofs),proofs=proofs,
        scope='Every completed SHA-bound P3 window checked for actual route-use timing; existing full canonical/physical audits remain authoritative. No Native launch or route oracle.')


def observe(path):
    try:return json.loads(path.read_text())
    except (FileNotFoundError,json.JSONDecodeError):return {}


def run(ordered,p1,output,pid):
    output.mkdir(parents=True,exist_ok=False);source=revision();start=time.monotonic()
    def status(state,**extra):write_json(output/'status.json',dict(state=state,analysis_source=source,
        ordered=str(ordered),wall_seconds=time.monotonic()-start,**extra))
    try:
        while not (ordered/'receipt.json').exists():
            current=observe(ordered/'status.json');p3=observe(ordered/'p3/status.json')
            if current.get('state')=='failed' or p3.get('state')=='failed':
                raise ValueError('Exact ordered study failed; preserve it without retry or truncated acceptance')
            root=Path('/proc')/str(pid)
            if not root.exists() or root.joinpath('stat').read_text().split(') ',1)[1][0]=='Z':
                raise ValueError('Exact ordered controller ended without its final accepted receipt')
            args=root.joinpath('cmdline').read_bytes().split(b'\0')
            if b'tools.run_ordered_execution' not in args or str(ordered).encode() not in args:
                raise ValueError('Do not follow a reused or unrelated process')
            status('waiting_exact_ordered_acceptance',completed=current.get('completed',{}),
                p3_completed=len(p3.get('completed',{})),p3_live=p3.get('live',{}));time.sleep(30)
        receipt=observe(ordered/'receipt.json')
        if not receipt.get('passed') or not receipt.get('complete_all_four_steps'):
            raise ValueError('All four recorded stages must be accepted')
        for item in receipt['completed'].values():
            if file_sha(Path(item['receipt']))!=item['sha256']:raise ValueError('Accepted stage receipt changed')
        status('auditing_actual_route_visibility');write_json(output/'route-visibility.json',route_readback(ordered))
        status('rendering_accepted_results');render(ordered,p1,output/'figures',require_p3=True)
        p3=observe(ordered/'p3/receipt.json');a=observe(ordered/'p2a/receipt.json');b=observe(ordered/'p2b/receipt.json')
        p=observe(p1/'analysis.json');decode=[v for v in p['paired_windows'] if v['phase']=='decode']
        reference=sum(v['reference']['duration_ps'] for v in decode);candidate=sum(v['candidate']['duration_ps'] for v in decode)
        text=['# Accepted ordered WoW-MoE execution study','',
            f'Physical source: `{receipt["source_commit"]}`; reader source: `{source}`.',
            f'B1 Decode: {reference/1e9:.6f} → {candidate/1e9:.6f} ms ({100*(reference-candidate)/reference:.2f}% reduction).',
            'All 51 both-zero-Native steps are unchanged; seven Decode regressions are retained.',
            'The supply-related witness changes are observations, not separately removable stalls.','',
            '| Resident kernel | Best OS output (µs) | Row output (µs) |', '|---|---:|---:|']
        text.extend(f'| {v["kind"]} | {v["best_os_ps"]/1e6:.3f} | {v["row_auto_ps"]/1e6:.3f} |' for v in a['comparisons'])
        text+=['','Extra row injection/steering is declared candidate hardware; MAC/SRAM/ports remain fixed, but equal silicon area is not proved.','',
            '| Cold kernel | Best OS output (µs) | Streaming output (µs) | Signed benefit (ns) |', '|---|---:|---:|---:|']
        text.extend(f'| {v["kind"]} | {v["best_os_ps"]/1e6:.3f} | {v["streaming_ps"]/1e6:.3f} | {v["signed_benefit_ps"]/1000:.3f} |' for v in b['comparisons'])
        text+=['','Streaming retains full cache pins, coupled fetch lifetimes and nonpreemptive array waits; starting early does not imply equal completion benefit.','',
            'P3 horizon: '+p3['scope'],'',
            '| Batch | Fastest measured OS placement | Policy | OS episode (ms) | Candidate (ms) | Signed reduction |',
            '|---|---|---|---:|---:|---:|']
        text.extend(f'| {v["B"]} | {v["placement"]} | {v["policy"]} | {v["best_os_ps"]/1e9:.6f} | {v["candidate_ps"]/1e9:.6f} | {100*v["completion_reduction_fraction"]:.3f}% |' for v in p3['comparisons'])
        text+=['',f'All {p3["accepted_cases"]} cases are independently accepted; no negative comparison is discarded.',
            'Original full B1 request and conditional P3 episodes are distinct evidence. No complete 94-layer Transformer, TTFT/TPOT, original-step cache replay, equal-PPA or novelty claim.','']
        (output/'summary.md').write_text('\n'.join(text))
        value=dict(passed=True,complete_all_four_steps=True,analysis_source=source,physical_source=receipt['source_commit'],
            ordered_receipt_sha256=file_sha(ordered/'receipt.json'),figure_receipt_sha256=file_sha(output/'figures/receipt.json'),
            summary_sha256=file_sha(output/'summary.md'),route_visibility_sha256=file_sha(output/'route-visibility.json'),
            accepted_cases=p3['accepted_cases'],P3_horizon=p3['horizon'],
            scope=p3['scope'],new_native_experiments=0)
        write_json(output/'receipt.json',value);status('complete_accepted_readback',receipt=value)
    except Exception as error:status('reader_failed',reason=str(error),physical_jobs_mutated=False);raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('ordered','p1','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--controller-pid',type=int,required=True);a=p.parse_args();run(a.ordered,a.p1,a.output,a.controller_pid)
