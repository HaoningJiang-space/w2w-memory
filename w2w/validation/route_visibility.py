"""Expert identity use must follow its actual modeled router completion."""


def audit_route_visibility(raw,index):
    ends={e['task']:e['time_ps'] for e in raw['events'] if e['kind']=='task_finish'}
    checks=0;groups=0
    for call in raw['runtime_metadata']['calls']:
        prefix=f'W{index:04d}/L{call["layer_id"]}/';router=prefix+'router_done'
        if router not in ends:raise ValueError('No completed router witnesses route visibility')
        members=tuple(prefix+f'e{e}/' for e in call['expert_token_counts']);groups+=len(members)
        for event in raw['events']:
            key=event.get('task','')
            expert=key.startswith(members)
            dispatch=key.startswith(prefix) and 'dispatch' in key[len(prefix):]
            if (expert or dispatch) and event['kind'] in ('task_allocate','read_issue','cache_lookup','task_start'):
                if event['time_ps']<ends[router]:raise ValueError('Captured future expert identity used before router completion')
                checks+=1
    if not checks:raise ValueError('No physical route uses were witnessed')
    return dict(passed=True,expert_groups=groups,checked_route_uses=checks,
        contract='Selected expert/dispatch admission, cache lookup, Native issue and compute start follow actual router completion. Trace-read identity is not hardware lookahead.')
