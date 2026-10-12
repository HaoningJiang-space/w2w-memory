"""Inspect existing array assignments and streaming prerequisites; no replay."""
import argparse,gzip,json,time,hashlib,datetime
from collections import Counter,defaultdict
from pathlib import Path

from w2w.analysis.moe_mechanism import read_mechanism_input,window_mechanism,distribution
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.io import write_json
from w2w.workloads.moe_trace import file_sha
from w2w.provenance import revision


def mapping_parts(kernel,plan,profile):
    rows,cols,arrays=(profile[k] for k in ('rows','columns','arrays'))
    ticks=[max(t['K'] for t in wave)+rows+cols-2 for wave in plan['waves']]
    if sum(ticks)!=plan['array_cycles']:raise ValueError('Stored array-core schedule differs from wave geometry')
    assigned=sum(len(wave)*n for wave,n in zip(plan['waves'],ticks))
    padded=sum(rows*cols*t['K'] for wave in plan['waves'] for t in wave)
    macs=kernel['M']*kernel['N']*kernel['K']
    if macs!=plan['macs']:raise ValueError('Mapped mathematical work differs')
    parts=dict(assigned_array_fraction=assigned/(arrays*sum(ticks)),
        spatial_shape_fraction=macs/padded,fill_drain_fraction=padded/(assigned*rows*cols),
        array_core_fraction=sum(ticks)/plan['cycles'])
    product=1
    for value in parts.values():product*=value
    if abs(product-plan['mac_utilization'])>1e-12:raise ValueError('Geometry/service utilization decomposition does not close')
    return dict(M=kernel['M'],N=kernel['N'],K=kernel['K'],k_partitions=plan['k_partitions'],
        arrays_per_wave=[len(w) for w in plan['waves']],array_cycles=plan['array_cycles'],
        service_cycles=plan['cycles'],service_efficiency=product,parts=parts,program_sha256=plan['program_sha256'])


def scale_observation(raw):
    issued=defaultdict(list);delivered={};edges={}
    for e in raw['events']:
        if e['kind']=='read_issue':issued[e['task']].append(e)
        elif e['kind']=='read_deliver':delivered[e['request']]=e['time_ps']
        elif e['kind']=='data_deliver':edges[e['edge']]=e['time_ps']
    incoming=defaultdict(list)
    for e in raw['graph']['data']:incoming[e['consumer']].append(e['id'])
    request_bytes=raw['spec']['memory_request_bytes'];rows=[]
    for key,k in raw['npu_execution']['kernels'].items():
        if not issued[key] or not key.endswith(('/gate','/up','/down')):continue
        weight=k['N']*k['K'];scales=4*((k['N']+127)//128)*((k['K']+127)//128)
        if k['weight_dtype']!='FP8_E4M3FN' or weight%request_bytes or not 0<scales<request_bytes:
            raise ValueError('This reader only labels the current full-row FP8 data/scale-tail descriptors')
        data=[e for e in issued[key] if e['bytes']==request_bytes]
        tail=[e for e in issued[key] if e['bytes']==scales]
        if len(tail)!=1 or sum(e['bytes'] for e in data)!=weight or len(data)+1!=len(issued[key]):
            raise ValueError('Weight/scale descriptor geometry changed')
        scale=tail[0];last_issue=max(e['time_ps'] for e in data)
        if scale['time_ps']<last_issue:raise ValueError('Frozen sequential scale-tail issue policy changed')
        last_weight=max(delivered[e['request']] for e in data);scale_ready=delivered[scale['request']]
        activation=max(edges[e] for e in incoming[key])
        rows.append(dict(task=key,kind=key.rsplit('/',1)[1],last_weight_issue_ps=last_issue,
            scale_issue_ps=scale['time_ps'],last_weight_commit_ps=last_weight,scale_commit_ps=scale_ready,
            activation_commit_ps=activation,scale_before_final_weight=scale_ready<last_weight,
            descriptor_level_tail_overlap_envelope_ps=max(0,last_weight-max(scale_ready,activation))))
    return dict(cold_expert_kernels=len(rows),scale_earlier_than_final_weight=sum(r['scale_before_final_weight'] for r in rows),
        tail_overlap_envelope_ps=distribution([r['descriptor_level_tail_overlap_envelope_ps'] for r in rows]),tasks=rows,
        scope='Current complete-descriptor commits only: input and all scales permit at most this remaining weight-delivery overlap. This does not establish N/K-tile readiness, available arrays/ports, attainable streaming cycles or additive savings. Reordering scale reads must pay the original physical requests.')


def run(study,mechanism,output):
    if output.exists():raise ValueError('Preserve prior readbacks')
    begin=time.monotonic();m=json.loads(mechanism.read_text());reg=json.loads((study/'registration.json').read_text())
    if not m.get('passed') or m['case']!='B1-reference':raise ValueError('Accepted Reference mechanism required')
    for path,sha in m['sources'].items():
        if file_sha(Path(path))!=sha:raise ValueError('Accepted Reference source changed')
    sources={str(mechanism):file_sha(mechanism)};summary=json.load(gzip.open(study/'cases/B1-reference/result.json.gz','rt'));windows=[]
    for index in (2,27):
        row=summary['runtime_windows']['windows'][index];path=study/'cases/B1-reference/windows'/row['file']
        if row['sha256']!=m['windows'][index]['source_sha256']:raise ValueError('Reference archive binding changed')
        raw=read_mechanism_input(path,row['sha256']);sources[str(path)]=row['sha256'];metrics=window_mechanism(raw)
        if (metrics['duration_ps'],metrics['array_macs'],metrics['array_service_cycles'])!=(m['windows'][index]['duration_ps'],m['windows'][index]['array_macs'],m['windows'][index]['array_service_cycles']):
            raise ValueError('Reconstructed observed Reference work changed')
        npu=raw['npu_execution'];counts=Counter();shapes={}
        for key,k in npu['kernels'].items():
            if not key.endswith(('/gate','/up','/down')):continue
            kind=key.rsplit('/',1)[1];parts=mapping_parts(k,npu['plans'][key],npu['profile'])
            if kind in shapes and shapes[kind]!=parts:raise ValueError('Do not summarize unequal expert programs as one shape')
            shapes[kind]=parts;counts[kind]+=1
        gateways={g['id']:g for g in raw['spec']['stack']['gateways']};period=raw['spec']['noc_period_ps']
        windows.append(dict(decode_step=index-2,kernels_per_kind=dict(counts),shapes=shapes,
            duration_ps=metrics['duration_ps'],native_bytes=metrics['native_bytes'],
            gateway_work_bound_ps=max((b*period/gateways[g]['data_bytes_per_cycle'] for g,b in metrics['gateway_bytes'].items()),default=0),
            reference_shared_service_work_bound_ps=max(c['arithmetic_service_ps'] for c in metrics['clusters'].values()),
            mac_only_global_budget_bound_ps=metrics['array_macs']*npu['profile']['period_ps']/(npu['profile']['arrays']*npu['profile']['rows']*npu['profile']['columns']*len(raw['spec']['stack']['compute_clusters'])),
            scales=scale_observation(raw)))
    # Preserve an explicitly provisional first-window comparison. Original
    # progress may advance; immutable raw SHA and the observed snapshot bind it.
    progress=study/'cases/B1-phase_split/windows/progress.json';partial=None
    if progress.exists():
        snapshot=progress.read_bytes();latest=json.loads(snapshot)['latest']
        if latest['index']==0:
            path=study/'cases/B1-phase_split/windows'/latest['file'];raw=read_mechanism_input(path,latest['sha256'])
            sources[str(path)]=latest['sha256'];metrics=window_mechanism(raw);a=m['windows'][0]
            if (digest(raw['spec'])!=reg['machine_sha256'] or raw['npu_execution']['profile']!=m['npu_profile']
                    or digest(raw['graph']['objects'])!=reg['cases']['B1-phase_split']['catalog_sha256']
                    or metrics['groups']!=a['groups'] or metrics['array_macs']!=a['array_macs']
                    or metrics['array_service_cycles']!=a['array_service_cycles']):raise ValueError('Provisional first window differs in workload/budget')
            partial=dict(index=0,reference_duration_ps=a['duration_ps'],phase_split_duration_ps=metrics['duration_ps'],
                signed_delta_ps=a['duration_ps']-metrics['duration_ps'],reference_native_bytes=a['native_bytes'],
                phase_split_native_bytes=metrics['native_bytes'],local_window_audits={k:latest[k] for k in ('audit','control_audit','npu_audit')},
                progress_snapshot_sha256=hashlib.sha256(snapshot).hexdigest(),complete_case=False,paired_gate_accepted=False,
                scope='Only the first 32-token Prefill window, same actual route/array work/resource budget. Local window audits and event reconstruction pass; no final independent complete-case/carry-chain acceptance or overall speedup claim.')
    value=dict(passed=True,analysis_source=revision(),observed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),sources=sources,
        reference_windows=windows,provisional_phase_split=partial,wall_seconds=time.monotonic()-begin,
        scope='Read-only actual mapped-array decomposition and scale/input prerequisites for original steps 0/25, with a separately provisional first Phase-Split window. No new physical experiments, hardware policy, idle-array inference from low MAC utilization, streaming feasibility or architecture acceptance. Reference shared-grant work is a lower bound for its serialized schedule; a changed fabric can change that work bound.')
    write_json(output,value);return value


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','mechanism','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.study,a.mechanism,a.output)
