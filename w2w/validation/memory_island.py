"""Saved-record comparison, independent of the native service implementation."""
from copy import deepcopy


def _physical(raw):
    r=deepcopy(raw)
    r.pop('kernel_iterations');r.pop('memory_island',None)
    for field in ('source_commit','audit','control_audit'):r.pop(field,None)
    r['network'].pop('runtime_source',None)
    for field in ('binary_sha256','config_sha256'):r['network']['identity'].pop(field,None)
    r['native'].pop('config_sha256',None)
    for controller in r['native']['config']['memory_system']['controllers']:
        for plugin in controller['controller_plugins']:
            if plugin['impl']=='CmdTraceRecorder':plugin['path']='commands'
    return r


def audit_memory_island_pair(raw,reference,wakes,reference_wakes):
    if _physical(raw)!=_physical(reference):raise ValueError('Island physical interface or service record differs')
    if (len(wakes)!=raw['kernel_iterations'] or wakes!=sorted(set(wakes))
            or len(reference_wakes)!=reference['kernel_iterations']):raise ValueError('Invalid island clock evidence')
    periods={reference['spec']['noc_period_ps'],reference['spec']['dram_period_ps'],
        *(t['compute_period_ps'] for t in reference['spec']['tiles'])}
    union=sorted({at for period in periods for at in range(0,reference['drained_ps']+1,period)})
    if reference_wakes!=union:raise ValueError('Reference clock union incomplete')
    omitted=set(union)-set(wakes)
    if set(wakes)-set(union) or any(at%reference['spec']['noc_period_ps']==0 for at in omitted):
        raise ValueError('Omitted external service boundary')
    c=raw.get('memory_island')
    if c is not None:
        keys={'schema','kind','host_advances','native_advances','internal_frontend_steps','dram_ticks','contract'}
        if set(c)!=keys or c['schema']!=1 or c['kind']!='one_domain_native_memory_service':
            raise ValueError('Unknown island coordination evidence')
        if (c['host_advances']!=len(wakes) or c['dram_ticks']!=raw['drained_ps']//raw['spec']['dram_period_ps']
                or not 1<=c['native_advances']<=c['host_advances']
                or not c['dram_ticks']<=c['internal_frontend_steps']<=len(union)):
            raise ValueError('Island update totals differ from clock evidence')
    elif omitted:raise ValueError('Omitted clocks without island execution')
    return dict(physical_record_equal=True,omitted_dram_only_wakes=len(omitted),all_noc_boundaries_retained=True)
