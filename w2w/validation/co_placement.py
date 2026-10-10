"""Independent contract for fixed-weight, Up-only compute interventions."""
from collections import Counter


def up_work_by_cluster(data):
    work=data['metadata']['task_work'];rows=Counter()
    for t in data['graph']['tasks']:
        if t['id'].endswith('/up'):
            w=work[t['id']]
            rows[t['tile'],'tasks']+=1;rows[t['tile'],'macs']+=w['macs']
            rows[t['tile'],'weight_bytes']+=sum(r['size_bytes'] for r in t['reads'])
            rows[t['tile'],'scratch_bytes']+=t['scratch_bytes']
    return dict(rows)


def audit_co_placement_inputs(inputs):
    if set(inputs)-{'reference_compute','up_local_compute','up_matched_nonlocal'}:
        raise ValueError('Unknown co-placement intervention')
    base=inputs['reference_compute'];graph=base['graph'];tasks={t['id']:t for t in graph['tasks']}
    stack=base['machine'];clusters={c['id']:c for c in stack['compute_clusters']}
    groups={g['id']:g for g in stack['bank_groups']};gateways={g['id']:g for g in stack['gateways']}
    objects={o['id']:o for o in graph['objects']}
    def local(name):
        gateway=gateways[groups[objects[name]['memory']]['gateway_id']]
        cs=[c['id'] for c in clusters.values() if c['router_id']==gateway['router_id'] and c['position_um']==gateway['position_um']]
        if len(cs)!=1:raise ValueError('Ambiguous/non-co-located physical Gateway consumer')
        return cs[0]
    def untile(task):return {k:v for k,v in task.items() if k!='tile'}
    for case,data in inputs.items():
        if data['projection_policy']!=case:raise ValueError('Co-placement policy identity changed')
        for field in ('machine','resources','weights','compute_reference_weights','network_policy',
                      'compute_contexts','operand_readiness','refresh','request_control','fetch_policy','mode'):
            if data[field]!=base[field]:raise ValueError('Co-placement changed fixed '+field)
        for field in ('objects','data','control'):
            if data['graph'][field]!=graph[field]:raise ValueError('Co-placement changed weight addresses or mathematical edges')
        if data['metadata']['task_work']!=base['metadata']['task_work']:raise ValueError('Co-placement changed arithmetic/services')
        if len(data['graph']['tasks'])!=len(tasks):raise ValueError('Co-placement changed task count')
        for t in data['graph']['tasks']:
            if t['id'] not in tasks or untile(t)!=untile(tasks[t['id']]):raise ValueError('Co-placement changed task semantics')
            old=tasks[t['id']]
            if not t['id'].endswith('/up'):
                if t['tile']!=old['tile']:raise ValueError('Co-placement moved non-Up arithmetic')
                continue
            name=t['stream']['weight_object'];near=local(name)
            if clusters[t['tile']]['profile']!=clusters[old['tile']]['profile']:raise ValueError('Compute profile changed')
            if case=='up_local_compute' and t['tile']!=near:raise ValueError('Up-local arithmetic is remote from its actual Gateway')
            if case=='up_matched_nonlocal':
                if t['tile'] in (near,old['tile']) or clusters[t['tile']]['reticle_id']!=clusters[near]['reticle_id']:
                    raise ValueError('Nonlocal diagnostic is not a moved, same-reticle nonlocal Up')
        cache=data['cache'];old_cache=base['cache']
        if (cache is None)!=(old_cache is None):raise ValueError('Cache enabled only in one case')
        if cache:
            if case=='up_matched_nonlocal':raise ValueError('Matched nonlocal is cold-only')
            if {k:v for k,v in cache.items() if k!='initial_resident'}!={k:v for k,v in old_cache.items() if k!='initial_resident'}:
                raise ValueError('Cache service/capacity changed')
            initial=cache['initial_resident'];old_initial=old_cache['initial_resident']
            if [x[1] for x in initial]!=[x[1] for x in old_initial] or len({tuple(x) for x in initial})!=len(initial):
                raise ValueError('Initial cache objects/order/replicas changed')
            amounts=Counter();entries=Counter()
            for (tile,name),(old_tile,_) in zip(initial,old_initial):
                target=local(name) if case=='up_local_compute' and name.endswith('/up') else old_tile
                if tile!=target:raise ValueError('Cache preload retained a free remote Up hit or moved a non-Up object')
                amounts[tile]+=objects[name]['size_bytes'];entries[tile]+=1
            if (any(n>cache['data_bytes_per_cluster'] for n in amounts.values()) or
                    any(n>cache['entries_per_cluster'] for n in entries.values())):
                raise ValueError('Mapped full catalog exceeds finite per-cluster cache')
    if 'up_matched_nonlocal' in inputs:
        if 'up_local_compute' not in inputs:raise ValueError('Nonlocal diagnostic requires its matched Up-local cell')
        if up_work_by_cluster(inputs['up_matched_nonlocal'])!=up_work_by_cluster(inputs['up_local_compute']):
            raise ValueError('Nonlocal diagnostic changed the matched per-cluster Up work')
    return dict(passed=True,cases=list(inputs),tasks=len(tasks),catalog_matrices=len(objects),
        contract='Same physical machine, weight addresses, work and mathematical data/control edges; only Up task tiles change. '
                 'Cold nonlocal matches per-cluster Up work but does not freeze dynamic arbitration or input path length. '
                 'Warm preload moves actual Up storage to its consumer, retains the full L0 catalog/order and pays finite per-cluster capacity; subsequent traffic may differ.')
