"""Independent fetch eligibility and unchanged mathematical-start audit."""
from collections import Counter,defaultdict


def audit_down_prefetch(result):
    record=result.get('down_prefetch')
    if not record:raise ValueError('Explicit whole-matrix prefetch evidence required')
    plan=record['plan'];tasks={t['id']:t for t in result['graph']['tasks']};pred=defaultdict(set)
    if (plan['policy']!='whole-down-spare-slot-v1' or plan['waiting_down_per_cluster']!=1
            or plan['metadata_bytes_per_cluster']!=8 or result['fetch_execution']['contexts_per_cluster']!=2
            or result['compute_execution']['contexts_per_cluster']!=2 or record['live_waiting']):
        raise ValueError('Bounded whole-matrix resources changed')
    from w2w.common.fingerprints import digest_read_v1
    if plan['graph_sha256']!=digest_read_v1(result['graph']):raise ValueError('Prefetch plan attached to another graph')
    for edge in (*result['graph']['data'],*result['graph']['control']):pred[edge['consumer']].add(edge['producer'])
    rows={row['task']:row for row in plan['releases']}
    expected={key for key,t in tasks.items() if key.endswith('/down') and t['stream']}
    if len(rows)!=len(plan['releases']) or set(rows)!=expected:raise ValueError('Missing or duplicate Down association')
    for key,row in rows.items():
        gate,up=key[:-4]+'gate',key[:-4]+'up'
        if (tuple(row['demand_tasks'])!=(gate,up) or gate in pred[up]
                or tuple(row['fetch_predecessors'])!=tuple(sorted(pred[gate]|pred[up]))):
            raise ValueError('Fetch eligibility changed rather than separating the original S1 boundary')
    allocated={};started={};done={};live={};peak=Counter();early=[];reserved=Counter();freed=Counter()
    for e in result['events']:
        key=e.get('task');at=e['time_ps'];kind=e['kind']
        if kind=='sram_change' and e['task']=='down-prefetch-state':
            (reserved if e['bytes']>0 else freed)[e['tile']]+=abs(e['bytes'])
        if kind=='task_finish':done[key]=at
        elif kind=='task_allocate':
            if key in rows:
                row=rows[key];tile=tasks[key]['tile']
                if (at<tasks[key]['release_ps'] or any(p not in done for p in row['fetch_predecessors'])
                        or any(p not in allocated for p in row['demand_tasks']) or tile in live):
                    raise ValueError('Down prefetch before dependency/demand admission or over capacity')
                if any(p not in done for p in pred[key]):early.append(key)
            allocated[key]=at
        elif kind=='down_prefetch_acquire':
            tile=tasks[key]['tile']
            if key not in rows or allocated.get(key)!=at or tile in live:raise ValueError('Invalid/repeated prefetch owner')
            live[tile]=key;peak[tile]=max(peak[tile],1)
        elif kind=='down_prefetch_release':
            tile=tasks[key]['tile']
            if live.pop(tile,None)!=key or at!=result['tasks'][key]['start_ps']:raise ValueError('Prefetch state released before mathematical compute start')
        elif kind=='task_start':
            if any(p not in done for p in pred[key]):raise ValueError('Original mathematical dependency bypassed')
            started[key]=at
    capacities={t['id']:8 for t in result['spec']['tiles']}
    if live or dict(peak)!=record['peak_waiting_by_cluster'] or dict(reserved)!=capacities or dict(freed)!=capacities:
        raise ValueError('Prefetch association/SRAM budget did not conserve and drain')
    if set(rows)-set(started):raise ValueError('Prefetched Down never computed')
    return dict(passed=True,down_tasks=len(rows),early_allocations=len(early),early_tasks=early,
        additional_metadata_bytes=sum(capacities.values()),same_graph_and_mathematical_start=True,
        contract='One waiting Down/cluster; two unchanged coupled fetch contexts; full SRAM storage, real native returns and original mathematical starts. Zero early allocations or negative speedup remain valid outcomes.')
