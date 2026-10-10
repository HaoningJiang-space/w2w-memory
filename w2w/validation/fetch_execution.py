"""Independent finite fetch-state, issue/outstanding and evidence-bin accounting."""
from collections import Counter,defaultdict


def audit_fetch_execution(result):
    policy=result.get('fetch_execution')
    if policy is None:return None
    if policy['metadata_bytes_per_cluster']!=policy['contexts_per_cluster']*64+8:raise ValueError('Unpaid fetch selector state')
    split=policy.get('lifetime_policy','until_operands')=='issue_only'
    if split and not policy.get('return_tracking'):raise ValueError('Issue-only state has no finite return table')
    tasks={t['id']:t for t in result['graph']['tasks']};live=defaultdict(set);peak=Counter();read=Counter();issued=Counter()
    requests={};outstanding=Counter();out_peak=Counter();issue=Counter();funding=defaultdict(list)
    for event in result['events']:
        kind=event['kind'];key=event.get('task');at=event['time_ps']
        if kind=='sram_change' and key=='fetch-context-state':funding[event['tile']].append(event['bytes'])
        elif kind=='fetch_context_acquire':
            tile=tasks[key]['tile']
            if key in live[tile]:raise ValueError('Fetch state acquired twice')
            live[tile].add(key);peak[tile]=max(peak[tile],len(live[tile]))
            if len(live[tile])>policy['contexts_per_cluster']:raise ValueError('Fetch context budget exceeded')
        elif kind=='read_issue':
            tile=tasks[key]['tile']
            if key not in live[tile]:raise ValueError('Read issued without bounded fetch ownership')
            requests[event['request']]=key;outstanding[tile]+=1;out_peak[tile]=max(out_peak[tile],outstanding[tile]);issue[tile,at]+=1
            issued[key]+=event['bytes']
            if outstanding[tile]>result['spec']['outstanding_per_tile'] or issue[tile,at]>result['spec']['read_requests_per_tile_cycle']:
                raise ValueError('Shared read issue or outstanding limit exceeded')
        elif kind=='read_deliver':
            read[key]+=event['bytes'];outstanding[tasks[key]['tile']]-=1
        elif kind=='cache_operands_ready':read[key]+=event['bytes']
        elif kind=='fetch_context_release':
            tile=tasks[key]['tile']
            completed=issued[key] if split else read[key]
            if key not in live[tile] or completed!=sum(r['size_bytes'] for r in tasks[key]['reads']):raise ValueError('Fetch state released before its declared lifetime boundary')
            live[tile].remove(key)
    if any(live.values()) or any(outstanding.values()) or policy['live_contexts'] or dict(peak)!=policy['peak_contexts']:
        raise ValueError('Fetch state or requester lifecycle did not drain')
    for tile in (t['id'] for t in result['spec']['tiles']):
        if funding[tile]!=[policy['metadata_bytes_per_cluster'],-policy['metadata_bytes_per_cluster']]:raise ValueError('Fetch state was not reserved inside existing SRAM')
    if dict(out_peak)!=result['outstanding_peak']:raise ValueError('Independent outstanding peak differs')
    if split:
        from .return_tracking import audit_return_tracking
        audit_return_tracking(result)
    return dict(passed=True,contexts_per_cluster=policy['contexts_per_cluster'],peak_contexts=dict(peak),
        metadata_bytes_per_cluster=policy['metadata_bytes_per_cluster'],issue_and_outstanding_shared=True)


def audit_gateway_bins(result):
    trace=result['native'].get('gateway_service_bins')
    if trace is None:return
    gateways={g['id']:g for g in result['spec']['stack']['gateways']};native=result['native'];period=result['spec']['noc_period_ps']
    for key,rows in trace['gateways'].items():
        bytes_=busy=0;seen=set()
        for row in rows:
            start,end=row['start_ps'],row['end_ps']
            if start in seen or end-start!=trace['interval_ps'] or start%trace['interval_ps']:raise ValueError('Malformed gateway service evidence bin')
            seen.add(start);bytes_+=row['bytes'];busy+=row['busy_cycles']
            if row['busy_cycles']>(end-start)//period or row['bytes']>row['busy_cycles']*gateways[key]['data_bytes_per_cycle']:
                raise ValueError('Gateway evidence claims excess service')
        if bytes_!=native['gateway_bytes'].get(key,0) or busy!=native['gateway_busy_cycles'].get(key,0):raise ValueError('Gateway bins disagree with actual service')
    if set(native['gateway_bytes'])-set(trace['gateways']):raise ValueError('Gateway service omitted from time series')
