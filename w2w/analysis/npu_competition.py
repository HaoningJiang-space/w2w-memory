"""Observed shape-aware NPU boundaries, not recoverable application stalls.

The five intervals partition each task's dependency-ready to finish span. They
can overlap other tasks, and capacity intersections do not identify a unique
cause. This reader supports both explicit cycles and fixed array epochs.
"""
from collections import Counter, defaultdict
from .compute_memory_competition import Occupancy


def competition(result):
    tasks={t['id']:t for t in result['graph']['tasks']}
    npu=result['npu_execution'];kernels=npu['kernels']
    parents=defaultdict(set);inputs=defaultdict(list)
    for e in (*result['graph']['control'],*result['graph']['data']):parents[e['consumer']].add(e['producer'])
    for e in result['graph']['data']:inputs[e['consumer']].append(e['id'])
    allocated={};started={};finished={};read_done={};cache_done={};edge_done={};first_grant={};busy=Counter()
    contexts=defaultdict(list);fetches=defaultdict(list)
    periods={t['id']:t['compute_period_ps'] for t in result['spec']['tiles']}
    for e in result['events']:
        kind=e['kind'];key=e.get('task');at=e['time_ps']
        if kind=='data_deliver':edge_done[e['edge']]=at
        if key not in tasks:continue
        tile=tasks[key]['tile']
        if kind=='task_allocate':
            if key in allocated:raise ValueError('Repeated task allocation')
            allocated[key]=at
        elif kind in ('task_start','task_finish'):
            target=started if kind=='task_start' else finished
            if key in target:raise ValueError('Repeated task start/finish')
            target[key]=at;contexts[tile].append((at,key,kind=='task_start'))
        elif kind in ('fetch_context_acquire','fetch_context_release'):
            fetches[tile].append((at,key,kind=='fetch_context_acquire'))
        elif kind=='read_deliver':read_done[key]=at
        elif kind in ('cache_operands_ready','npu_cached_operands_ready'):cache_done[key]=at
        elif kind in ('npu_epoch','npu_cycle','compute_service'):
            first_grant.setdefault(key,at)
            busy[key]+=e.get('cycles',1)*periods[tile]
    if set(allocated)!=set(tasks) or set(started)!=set(tasks) or set(finished)!=set(tasks):
        raise ValueError('NPU competition requires a completed physical graph')
    context={t:Occupancy(changes,result['compute_execution']['contexts_per_cluster']) for t,changes in contexts.items()}
    fetch={t:Occupancy(changes,result['fetch_execution']['contexts_per_cluster']) for t,changes in fetches.items()}
    origin=result.get('runtime_window_begin_ps',0);rows={};clusters=defaultdict(Counter)
    fields=('eligible_to_admit_ps','admit_to_operands_ps','operands_to_start_ps','start_to_first_grant_ps','first_grant_to_finish_ps')
    for key,task in tasks.items():
        tile=task['tile'];a=allocated[key];s=started[key];c=finished[key]
        r=max(origin,task['release_ps'],max((finished[p] for p in parents[key]),default=origin))
        if task['reads'] and key not in read_done and key not in cache_done:raise ValueError('Missing committed weight boundary')
        o=max(a,read_done.get(key,a),cache_done.get(key,a),max((edge_done[e] for e in inputs[key]),default=a))
        g=first_grant.get(key,s)
        boundary=(r,a,o,s,g,c)
        if list(boundary)!=sorted(boundary):raise ValueError('Task admission/operand/compute boundaries are not causal')
        intervals={f:y-x for f,x,y in zip(fields,boundary,boundary[1:])}
        if sum(intervals.values())!=c-r:raise ValueError('Task boundary span did not conserve time')
        if key in kernels and (busy[key]!=npu['plans'][key]['cycles']*periods[tile] or g+busy[key]!=c):
            raise ValueError('Nonpreemptive array ownership did not close')
        if busy[key]>c-s:raise ValueError('Arithmetic service exceeds owned context interval')
        row=dict(task=key,tile=tile,kernel=key in kernels,dependency_ready_ps=r,admitted_ps=a,
            operands_committed_ps=o,context_start_ps=s,first_grant_ps=g,completed_ps=c,
            observed_intervals_ps=intervals,arithmetic_service_ps=busy[key],context_owned_ps=c-s,
            compute_context_full_before_start_ps=context[tile].blocked_time(o,s),
            fetch_full_before_admit_ps=fetch[tile].blocked_time(r,a) if task['reads'] and tile in fetch else 0,
            nonservice_after_start_ps=c-s-busy[key],cache_hit=key in cache_done)
        if key in kernels:row['shape']={f:kernels[key][f] for f in ('M','N','K')}
        rows[key]=row;clusters[tile]['tasks']+=1;clusters[tile]['context_owned_ps']+=c-s
        clusters[tile]['arithmetic_service_ps']+=busy[key]
        clusters[tile].update(intervals)
    for tile,owned in context.items():
        if owned.area!=result['engine_context_ps'][tile] or clusters[tile]['context_owned_ps']!=owned.area:
            raise ValueError('Reconstructed context lifetime differs from execution ledger')
        if clusters[tile]['arithmetic_service_ps']!=result['compute_busy_ps'][tile]:raise ValueError('Reconstructed shared service differs from execution ledger')
    pairs={}
    for key in kernels:
        if not key.endswith('/gate'):continue
        up=key[:-4]+'up'
        if up not in kernels:raise ValueError('Gate projection has no matching Up')
        gate=rows[key];other=rows[up];join=max(gate['completed_ps'],other['completed_ps'])
        pairs[key.rsplit('/',1)[0]]=dict(gate=key,up=up,joint_ready_ps=join,
            last_projection='tie' if gate['completed_ps']==other['completed_ps'] else ('gate' if gate['completed_ps']>other['completed_ps'] else 'up'),
            early_projection_slack_ps=abs(gate['completed_ps']-other['completed_ps']))
    return dict(tasks=rows,clusters={t:dict(v) for t,v in clusters.items()},projection_pairs=pairs,
        scope='Observed integer-ps dependency/admission/complete-operand/context/grant boundaries. Task spans are disjoint within a task but overlap across tasks. Full-capacity intersections and latest projections do not establish counterfactual savings or an exclusive responsible resource. Complete-operand OS policy is a model assumption, not proof of optimal streaming dataflow.')
