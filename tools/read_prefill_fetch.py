"""Read existing Prefill slot/gateway evidence; never execute or alter hardware."""
import argparse,gzip,json,time
from collections import defaultdict
from pathlib import Path

from w2w.analysis.compute_memory_competition import Occupancy
from w2w.common.event_archive import _read_integers
from w2w.common.io import write_json
from w2w.workloads.moe_trace import file_sha
from w2w.provenance import revision


def columns(codec,kind,fields):
    column=next(c for c in codec['columns'] if c['kind']==kind);result={}
    for key in fields:
        field=column['fields'][key]
        if field['count']!=column['count'] or 'present' in field:raise ValueError('Complete milestone fields required')
        if field['encoding'] in ('delta-integers','strings'):
            values=_read_integers(field['values'],field['count'])
            if field['encoding']=='strings':values=[codec['strings'][v] for v in values]
        elif field['encoding']=='json':values=field['values']
        else:raise ValueError('Unsupported milestone encoding')
        if len(values)!=column['count']:raise ValueError('Incomplete milestone column')
        result[key]=values
    if result['time_ps']!=sorted(result['time_ps']):raise ValueError('Nonmonotonic physical milestone column')
    return result


def pool_ownership(raw,wanted):
    memories={m['id']:m for m in raw['spec']['memories']};codec=raw['events_codec']
    accepted=columns(codec,'mc_accept',('time_ps','request','memory'))
    released=columns(codec,'mc_release',('time_ps','request','memory'))
    opened={};changes=defaultdict(list);area=defaultdict(int)
    for at,key,mem in zip(accepted['time_ps'],accepted['request'],accepted['memory']):
        pool=memories[mem].get('mc_pool_id') or mem
        if pool in wanted:
            if key in opened:raise ValueError('Duplicate MC acceptance')
            opened[key]=(at,mem);changes[pool].append((at,key,True))
    for at,key,mem in zip(released['time_ps'],released['request'],released['memory']):
        pool=memories[mem].get('mc_pool_id') or mem
        if pool in wanted:
            start,original=opened.pop(key)
            if original!=mem or start>=at:raise ValueError('Invalid MC half-open lifetime')
            area[pool]+=at-start;changes[pool].append((at,key,False))
    if opened:raise ValueError('Undrained selected MC pools')
    result={}
    for pool in wanted:
        capacity=next(m['transaction_slots'] for m in memories.values() if (m.get('mc_pool_id') or m['id'])==pool)
        # Positive lifetimes; release-before-acquire at equal timestamps only
        # specifies half-open wall-time accounting, not original micro-order.
        owner=Occupancy(sorted(changes[pool],key=lambda e:(e[0],e[2])),capacity)
        if owner.area!=area[pool]:raise ValueError('MC slot area differs from descriptor lifetimes')
        result[pool]=owner
    return result


def gateway_bounds(raw,gateway,begin,end):
    evidence=raw['native']['gateway_service_bins'];bins=evidence['gateways'].get(gateway,[])
    complete=[b for b in bins if begin<=b['start_ps'] and b['end_ps']<=end]
    boundary=[b for b in bins if b['start_ps']<end and b['end_ps']>begin and not (begin<=b['start_ps'] and b['end_ps']<=end)]
    lower=sum(b['bytes'] for b in complete);upper=lower+sum(b['bytes'] for b in boundary)
    period=raw['spec']['noc_period_ps'];capacity=next(g['data_bytes_per_cycle'] for g in raw['spec']['stack']['gateways'] if g['id']==gateway)
    cycles=(end-begin)/period
    return dict(payload_bytes_lower=lower,payload_bytes_upper=upper,
        busy_fraction_lower=sum(b['busy_cycles'] for b in complete)/cycles,
        busy_fraction_upper=min(1,sum(b['busy_cycles'] for b in (*complete,*boundary))/cycles),
        payload_capacity_fraction_lower=lower/(cycles*capacity),payload_capacity_fraction_upper=upper/(cycles*capacity),
        bin_ps=evidence['interval_ps'],scope='Whole contained bins plus conservative boundary-bin bounds; no uniform-rate interpolation or inference of unused Native-domain opportunity.')


def run(study,mechanism,output):
    if output.exists():raise ValueError('Preserve prior readbacks')
    begin=time.monotonic();m=json.loads(mechanism.read_text());case=study/'cases/B1-reference'
    if not m.get('passed') or m['case']!='B1-reference':raise ValueError('Accepted Reference mechanisms required')
    for path,sha in m['sources'].items():
        if file_sha(Path(path))!=sha:raise ValueError('Accepted mechanism source changed')
    result=json.load(gzip.open(case/'result.json.gz','rt'));sources={str(mechanism):file_sha(mechanism)};windows=[]
    for index in (0,1):
        row=result['runtime_windows']['windows'][index];path=case/'windows'/row['file']
        if file_sha(path)!=row['sha256'] or m['windows'][index]['source_sha256']!=row['sha256']:
            raise ValueError('Complete previously audited Prefill archive changed')
        sources[str(path)]=row['sha256'];raw=json.load(gzip.open(path,'rt'))
        tasks={t['id']:t for t in raw['graph']['tasks']};objects={o['id']:o for o in raw['graph']['objects']};memories={x['id']:x for x in raw['spec']['memories']}
        witness=json.load(gzip.open(mechanism.parent/f'window-{index:04d}.json.gz','rt'));targets=sorted(witness['completion_witness']['tasks'],key=lambda t:t['observed_intervals_ps']['eligible_to_admit_ps'],reverse=True)[:2]
        sources[str(mechanism.parent/f'window-{index:04d}.json.gz')]=file_sha(mechanism.parent/f'window-{index:04d}.json.gz')
        pools={memories[objects[tasks[t['task']]['reads'][0]['object_id']]['memory']]['mc_pool_id'] for t in targets}
        ownership=pool_ownership(raw,pools);reads=[]
        for t in targets:
            mem=memories[objects[tasks[t['task']]['reads'][0]['object_id']]['memory']];a=t['dependency_ready_ps'];b=t['admitted_ps']
            reads.append(dict(task=t['task'],tile=t['tile'],eligible_ps=a,admitted_ps=b,admission_ps=b-a,
                fetch_full_ps=t['fetch_full_before_admit_ps'],pool=mem['mc_pool_id'],gateway=mem['gateway_id'],
                mc_pool_full_ps=ownership[mem['mc_pool_id']].blocked_time(a,b),mc_pool_capacity=mem['transaction_slots'],
                gateway_service=gateway_bounds(raw,mem['gateway_id'],a,b)))
        windows.append(dict(index=index,targets=reads))
    value=dict(passed=True,analysis_source=revision(),sources=sources,windows=windows,wall_seconds=time.monotonic()-begin,
        scope='Read-only selected long admission spans from two original complete Prefill archives, bound to prior full physical audits. MC wall-time occupancy uses positive descriptor half-open lifetimes; original micro-order and full Native-domain/control audits remain authoritative. Gateway service has explicit 1-us boundary-bin bounds. This is not whole-phase causal attribution, a new physical audit, proof of available bandwidth or an intervention/speedup claim.')
    write_json(output,value);return value


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','mechanism','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.study,a.mechanism,a.output)
