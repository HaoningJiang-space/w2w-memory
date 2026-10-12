"""Separate complete captured B1 phases and reconstruct every window's events."""
import argparse,csv,gzip,json,time
from pathlib import Path

from w2w.analysis.moe_mechanism import window_mechanism,phase_summary,read_mechanism_input
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.io import write_json
from w2w.provenance import revision
from w2w.workloads.moe_trace import file_sha


def run(study,case,output,accepted_analysis=None):
    directory=study/'cases'/case;analysis=accepted_analysis or directory/'analysis.json'
    reg=json.loads((study/'registration.json').read_text());a=json.loads(analysis.read_text())
    completion=json.loads((directory/'completion.json').read_text());path=directory/'result.json.gz';choice=reg['cases'][case]
    cohort=study/'cohorts'/reg['cohorts']['1']['file']
    if (choice['B']!=1 or not a.get('passed') or not completion.get('complete') or not a['full_captured_lifecycle']
            or a['case']!=case or a['source_commit']!=reg['source_commit'] or completion['source_commit']!=reg['source_commit']
            or a['registration_sha256']!=file_sha(study/'registration.json') or a['cohort_sha256']!=file_sha(cohort)
            or a['result_sha256']!=completion['result_sha256'] or a['result_sha256']!=file_sha(path)):
        raise ValueError('Complete accepted and hash-bound original B1 case required')
    summary=json.load(gzip.open(path,'rt'));windows=summary['runtime_windows']['windows']
    if len(windows)!=130 or completion['windows']!=130 or a['proof']['windows']!=130:raise ValueError('Complete original two-prefill/128-decode horizon required')
    output.mkdir(parents=True,exist_ok=False);begin=time.monotonic();rows=[];previous=None;end=0
    for index,row in enumerate(windows):
        source=directory/'windows'/row['file']
        if row['index']!=index or file_sha(source)!=row['sha256']:raise ValueError('Original complete event archive changed')
        raw=read_mechanism_input(source,row['sha256'])
        if raw.get('analysis_event_projection',{}).get('original_decoded_sha256',row['decoded_sha256'])!=row['decoded_sha256']:
            raise ValueError('Prior full decoded archive identity changed')
        if (digest(raw['spec'])!=reg['machine_sha256'] or digest(raw['graph']['objects'])!=choice['catalog_sha256']
                or raw['npu_execution']['profile']!=reg['npu_profile']
                or raw['weight_cache']['data_bytes_per_cluster']!=reg['cache']['data_bytes_per_cluster']
                or raw['runtime_window_begin_ps']!=end or row['begin_ps']!=end
                or digest(raw['runtime_carry_in'])!=row['carry_in_sha256'] or digest(raw['runtime_carry_out'])!=row['carry_out_sha256']
                or previous is not None and raw['runtime_carry_in']!=previous):
            raise ValueError('Physical resources or continuous carry changed')
        metrics=window_mechanism(raw);old=a['windows'][index]
        if (metrics['duration_ps'],metrics['native_bytes'],metrics['array_macs'],metrics['array_service_cycles'])!=(old['duration_ps'],old['native_bytes'],old['macs'],old['npu_service_cycles']):
            raise ValueError('Independent event reconstruction changed accepted observed work')
        metrics.update(source_sha256=row['sha256'],decoded_sha256=row['decoded_sha256'])
        with gzip.open(output/f'window-{index:04d}.json.gz','wt') as f:json.dump(metrics,f,separators=(',',':'))
        # Full witnessed tasks stay remote; compact step metrics remain reviewable.
        compact={k:v for k,v in metrics.items() if k not in ('completion_witness','clusters')}
        compact['completion_witness']={k:v for k,v in metrics['completion_witness'].items() if k!='tasks'}
        rows.append(compact);previous=raw['runtime_carry_out'];end=raw['drained_ps']
        write_json(output/'progress.json',dict(completed_windows=index+1,latest_index=index,phase=metrics['phase'],wall_seconds=time.monotonic()-begin))
        if index<2 or (index+1)%16==0:print(json.dumps(dict(completed_windows=index+1,phase=metrics['phase'],wall_seconds=time.monotonic()-begin)),flush=True)
    if [r['decode_step'] for r in rows if r['phase']=='decode']!=list(range(128)):
        raise ValueError('Original decode steps missing/repeated')
    phases=phase_summary(rows)
    if phases['prefill']['tokens']!=46 or phases['decode']['tokens']!=128:raise ValueError('Actual captured token horizon changed')
    spans=sum(r['duration_ps'] for r in rows);inter=sum(r['drained_ps']-r['makespan_ps'] for r in rows[:-1])
    if spans+inter!=summary['makespan_ps']:raise ValueError('Phases and inter-window drains do not close complete makespan')
    proof=dict(passed=True,schema='w2w.b1-moe-mechanism.v1',analysis_source=revision(),case=case,
        registration_sha256=a['registration_sha256'],cohort_sha256=a['cohort_sha256'],machine_sha256=reg['machine_sha256'],
        npu_profile=reg['npu_profile'],cache_budget=reg['cache'],sources={str(p):file_sha(p) for p in (analysis,directory/'completion.json',path,cohort,study/'registration.json')},
        accepted_resource_proof=a['proof'],phases=phases,windows=rows,inter_window_drain_ps=inter,
        makespan_ps=summary['makespan_ps'],drained_ps=summary['drained_ps'],wall_seconds=time.monotonic()-begin,
        scope='Every complete original B1 archive is byte-hash-bound to its prior full decoded physical/request/resource audit; only task/operand/service events are projected for this independent mechanism analysis. Actual task/context/grant ledgers, observed array service, continuous carry and one nonoverlapping completion witness per window close. Complete Native/NoC event archives and their accepted full audits are retained; this analysis projection is not a new complete canonical/resource audit. No exclusive bottleneck, recoverable-stall, silicon, complete Transformer or architecture-speedup claim.')
    write_json(output/'mechanism.json',proof)
    fields=('index','phase','decode_step','duration_ps','native_bytes','maximum_gateway_bytes','maximum_gateway_share',
        'array_service_cycles','array_service_efficiency','expert_array_service_efficiency','cache_misses','cache_hits','cache_reload_bytes',
        *('chain_'+x for x in ('eligible_to_admit_ps','admit_to_operands_ps','operands_to_start_ps','start_to_first_grant_ps','first_grant_to_finish_ps')))
    with (output/'steps.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in rows:
            line={k:r[k] for k in fields if k in r}
            line.update(cache_misses=r['cache_stats'].get('misses',0),cache_hits=r['cache_stats'].get('hits',0),cache_reload_bytes=r['cache_stats'].get('reload_bytes',0))
            line.update({'chain_'+k:v for k,v in r['completion_witness']['interval_totals_ps'].items()});writer.writerow(line)
    return proof


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','case','output'):p.add_argument('--'+name,type=Path if name!='case' else str,required=True)
    p.add_argument('--accepted-analysis',type=Path);a=p.parse_args();run(a.study,a.case,a.output,a.accepted_analysis)
