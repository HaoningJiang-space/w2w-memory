"""Reconstruct task milestones and context clock opportunities from committed events."""
import argparse,gzip,hashlib,json
from collections import Counter,defaultdict
from pathlib import Path
from w2w.common.io import write_json
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.provenance import revision


def stages(result):
    tasks={t['id']:t for t in result['graph']['tasks']}
    periods={c['id']:c['profile']['period_ps'] for c in result['spec']['stack']['compute_clusters']}
    rows={key:dict(task=key,tile=t['tile'],phase=key.rsplit('/',1)[-1],milestones={},
        busy_cycles=0,operand_wait_cycles=0,ready_service_wait_cycles=0) for key,t in tasks.items()}
    states={key:dict(active=False,last=None,granted=False,scale=False,prefix=0,consumed=0,pending={}) for key in tasks}
    final_operand={}
    requests={e['request']:e['task'] for e in result['events'] if e['kind']=='read_issue'}
    edges={e['id']:e for e in result['graph']['data']};delivered=Counter()
    def milestone(key,name,at):
        m=rows[key]['milestones'];m[name]=max(m.get(name,at),at)
    def advance(key,at):
        s=states[key];period=periods[tasks[key]['tile']]
        if s['last'] is not None and at<s['last']:raise ValueError('Nonmonotonic task event')
        if s['active'] and s['last'] is not None and at>s['last']:
            first=(s['last']+period-1)//period
            clocks=max(0,(at-1)//period-first+1)
            if s['granted'] and s['last']%period==0:clocks-=1
            stream=tasks[key]['stream']
            if stream is None or not s['scale'] or s['prefix']>s['consumed']:
                rows[key]['ready_service_wait_cycles']+=clocks
            elif s['consumed']<stream['weight_data_bytes']:
                rows[key]['operand_wait_cycles']+=clocks
            elif clocks:raise ValueError('Completed GEMM kept an unexplained live clock')
        if s['last']!=at:s['granted']=False
        s['last']=at
    native_names={'array_first_ready':'array_first_event','array_last_ready':'array_last_event',
        'native_first_ready':'gateway_first_ready','native_ready':'gateway_descriptor_ready',
        'mc_accept':'mc_accept','native_accept':'native_accept'}
    for e in result['events']:
        at=e['time_ps'];kind=e['kind'];key=e.get('task')
        if kind=='data_deliver':
            edge=edges[e['edge']];delivered[edge['id']]+=e['bytes']
            if delivered[edge['id']]==edge['size_bytes']:milestone(edge['consumer'],'input_ready',at)
            continue
        if kind in native_names:
            key=requests[e['request']];name=native_names[kind]
            m=rows[key]['milestones'];m.setdefault(name+'_first',at);m[name+'_last']=at
            continue
        if key not in tasks:continue
        if kind=='read_issue':
            m=rows[key]['milestones'];m.setdefault('read_issue_first',at);m['read_issue_last']=at
        elif kind=='task_allocate':milestone(key,'allocate',at)
        elif kind=='read_deliver':
            m=rows[key]['milestones'];m.setdefault('read_deliver_first',at);m['read_deliver_last']=at
        elif kind in ('task_start','task_finish','stream_operand_ready','cache_operands_ready','stream_compute','compute_service'):
            advance(key,at);s=states[key];stream=tasks[key]['stream']
            if kind=='task_start':s['active']=True;milestone(key,'start',at)
            elif kind=='task_finish':s['active']=False;milestone(key,'finish',at)
            elif kind=='cache_operands_ready':
                s['prefix']=stream['weight_data_bytes'];milestone(key,'scale_ready',at);milestone(key,'weight_ready_last',at)
            elif kind=='stream_operand_ready':
                offset=e['object_offset'];size=e['bytes']
                if offset>=stream['weight_data_bytes']:milestone(key,'scale_ready',at)
                else:
                    if offset<s['prefix'] or offset in s['pending']:raise ValueError('Duplicate stage operand')
                    s['pending'][offset]=size
                    while s['prefix'] in s['pending']:s['prefix']+=s['pending'].pop(s['prefix'])
                    if s['prefix']==stream['weight_data_bytes']:final_operand[key]=e['request']
                    m=rows[key]['milestones'];m.setdefault('weight_ready_first',at);m['weight_ready_last']=at
            else:
                s['granted']=True;rows[key]['busy_cycles']+=1
                m=rows[key]['milestones'];m.setdefault('service_first',at);m['service_last']=at
                if kind=='stream_compute':
                    s['scale']=True;s['consumed']+=e['weight_bytes']
                    if s['consumed']>s['prefix']:raise ValueError('Compute exceeded the committed prefix')
    predecessors=defaultdict(set)
    for edge in (*result['graph']['data'],*result['graph']['control']):predecessors[edge['consumer']].add(edge['producer'])
    aggregate={};by_invocation=defaultdict(dict);busy=Counter()
    for key,row in rows.items():
        t=tasks[key];m=row['milestones'];period=periods[t['tile']];executed=result['tasks'][key]
        if (m.get('start'),m.get('finish'))!=(executed['start_ps'],executed['finish_ps']):raise ValueError('Task milestone differs from execution')
        start,finish=m['start'],m['finish'];duration=finish-start
        if duration!=period*sum(row[name] for name in ('busy_cycles','operand_wait_cycles','ready_service_wait_cycles')):
            raise ValueError('Context clocks are not partitioned into service/operand/service-ready opportunities')
        dependency=max([t['release_ps'],*(result['tasks'][p]['finish_ps'] for p in predecessors[key])])
        m['dependency_ready']=dependency
        ready=max(m['allocate'],m.get('scale_ready',0),m.get('input_ready',0),dependency)
        row.update(context_ps=duration,dependency_to_allocate_ps=m['allocate']-dependency,
            start_after_required_inputs_ps=start-ready,
            busy_ps=row['busy_cycles']*period,operand_wait_ps=row['operand_wait_cycles']*period,
            ready_service_wait_ps=row['ready_service_wait_cycles']*period)
        if row['start_after_required_inputs_ps']<0:raise ValueError('Task started before required inputs')
        busy[t['tile']]+=row['busy_ps']
        def add(target):
            a=target.setdefault(row['phase'],dict(tasks=0,context_ps=0,busy_ps=0,operand_wait_ps=0,
                ready_service_wait_ps=0,dependency_to_allocate_ps=0,start_after_required_inputs_ps=0,first_start_ps=start,last_finish_ps=finish))
            a['tasks']+=1;a['first_start_ps']=min(a['first_start_ps'],start);a['last_finish_ps']=max(a['last_finish_ps'],finish)
            for field in ('context_ps','busy_ps','operand_wait_ps','ready_service_wait_ps','dependency_to_allocate_ps','start_after_required_inputs_ps'):a[field]+=row[field]
        add(aggregate)
        if key.startswith('I'):add(by_invocation[key.split('/')[0]])
    if dict(busy)!=result['compute_busy_ps']:raise ValueError('Stage service does not reproduce cluster busy accounting')
    terminal=max(rows,key=lambda k:(rows[k]['milestones']['finish'],k));chain=[];key=terminal
    while True:
        chain.append(rows[key])
        if not predecessors[key]:break
        key=max(predecessors[key],key=lambda k:(result['tasks'][k]['finish_ps'],k))
    pairs={}
    for key,row in rows.items():
        if not key.endswith('/gate'):continue
        up=key[:-4]+'up'
        if up not in rows:continue
        a,b=row['milestones'],rows[up]['milestones']
        def overlap(first,last):
            if any(first not in m or last not in m for m in (a,b)):return 0
            return max(0,min(a[last],b[last])-max(a[first],b[first]))
        pairs[key[:-5]]=dict(gate=key,up=up,fetch_window_overlap_ps=overlap('read_issue_first','weight_ready_last'),
            array_service_window_overlap_ps=overlap('array_first_event_first','array_last_event_last'),
            context_overlap_ps=overlap('start','finish'),both_projection_finish_ps=max(a['finish'],b['finish']))
    selected={final_operand[row['task']] for row in chain if row['task'] in final_operand}
    paths={req:dict(task=requests[req],events=[],links={}) for req in selected}
    for e in result['events']:
        req=e.get('request')
        if req in paths:
            if e['kind'] not in ('sram_change','stream_compute'):paths[req]['events'].append(e)
            continue
        packet=e.get('packet','');req=packet.rsplit('/',1)[0]
        if req not in paths:continue
        if e['kind']=='link_send':
            link=paths[req]['links'].setdefault((packet,e['link']),dict(packet=packet,link=e['link'],first_ps=e['time_ps'],last_ps=e['time_ps'],flits=0))
            link['last_ps']=e['time_ps'];link['flits']+=1
        elif e['kind'] in ('packet_accept','packet_deliver'):paths[req]['events'].append(e)
    event_level=result.get('network',{}).get('event_level','unknown')
    link_events_available=event_level=='flit'
    for value in paths.values():
        value['links']=list(value['links'].values())
        value['per_flit_link_events_available']=link_events_available
    return dict(phases=aggregate,invocations=dict(by_invocation),tasks=rows,
        latest_finishing_predecessor_chain=list(reversed(chain)),
        projection_pairs=pairs,tail_operand_paths=paths,network_event_level=event_level,
        contract='Reconstructs exact task milestones and shared-context clock opportunities. Operand wait means no consumable contiguous weight after scale service; '
            'ready-service wait means operands are ready but another grant/clock is awaited. Sums across tasks/contexts overlap; neither sums nor the latest-finishing '
            'dependency chain prove an exclusive system critical path through all implicit resource competition. Pair overlap measures interval overlap, not continuous busy time. '
            'Tail paths follow the descriptor that completes the consumed prefix along the observed finishing chain. '
            'Transaction-level captures retain packet admission/delivery, not per-flit link timestamps; empty links are not proof of a local path. '
            'Native array event timestamps retain their original convention.')


def analyze(source,audited):
    reg=json.loads((source/'registration.json').read_text());proof=json.loads(audited.read_text());cases={};raw={}
    if not proof['passed'] or proof['execution_source_commit']!=reg['source_commit']:raise ValueError('Completed independent audit required')
    for case,registered in reg['cases'].items():
        if registered['alias_of']:continue
        data=json.load(gzip.open(source/'inputs'/f'{case}.json.gz','rt'))
        if digest(data)!=registered['input_sha256']:raise ValueError('Stage input changed')
        path=source/'cases'/case/'result.json.gz';h=hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
        if h.hexdigest()!=proof['files'][str(path.relative_to(source))]['sha256']:raise ValueError('Audited raw record changed')
        r=json.load(gzip.open(path,'rt'))
        if r['graph']!=data['graph'] or r['makespan_ps']!=proof['cases'][case]['makespan_ps']:raise ValueError('Stage execution identity differs')
        cases[case]=dict(makespan_ps=r['makespan_ps'],**stages(r));raw[case]=h.hexdigest()
    return dict(schema='w2w.ffn-stage-analysis.v1',passed=True,execution_source_commit=reg['source_commit'],
        analysis_source_commit=revision(),cases=cases,raw_result_sha256=raw)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--audited',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=analyze(a.source,a.audited);write_json(a.output,r)
    print(json.dumps(dict(passed=True,cases={k:dict(makespan_ps=v['makespan_ps'],phases=v['phases']) for k,v in r['cases'].items()})))


if __name__=='__main__':main()
