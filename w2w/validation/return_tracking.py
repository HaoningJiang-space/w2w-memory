"""Independent replay of finite return associations, tags and paid SRAM."""
from collections import Counter,defaultdict
from math import ceil


def audit_return_tracking(result):
    policy=result['fetch_execution']['return_tracking'];spec=result['spec']
    tasks={t['id']:t for t in result['graph']['tasks']};live=defaultdict(dict);slots=defaultdict(set)
    bindings={};binding_count=Counter();peak=Counter();binding_peak=Counter();funding=defaultdict(list)
    issued=set();committed=set()
    expected_funding=policy['contexts_per_cluster']*16+spec['outstanding_per_tile']*8
    if (policy['association_bytes']!=16 or policy['binding_bytes_per_request']!=8 or
            policy['binding_capacity_per_cluster']!=spec['outstanding_per_tile'] or
            policy['metadata_bytes_per_cluster']!=expected_funding):raise ValueError('Unfunded return association/tag table')
    for e in result['events']:
        kind=e['kind'];key=e.get('task');tile=e.get('tile');slot=e.get('association')
        if kind=='sram_change' and key=='return-tracker-state':funding[tile].append(e['bytes'])
        elif kind=='return_context_acquire':
            expected=sum(ceil(r['size_bytes']/spec['memory_request_bytes']) for r in tasks[key]['reads'])
            if (key in live[tile] or slot in slots[tile] or not 0<=slot<policy['contexts_per_cluster'] or
                    expected!=e['expected_descriptors'] or len(live[tile])>=policy['contexts_per_cluster']):
                raise ValueError('Return association reused or overbooked')
            live[tile][key]=dict(slot=slot,expected=expected,bound=0,committed=0,issued=False)
            slots[tile].add(slot);peak[tile]=max(peak[tile],len(live[tile]))
        elif kind=='return_request_bind':
            req=e['request'];row=live[tile].get(key)
            if req in bindings or row is None or row['slot']!=slot:raise ValueError('Unknown or duplicate return tag association')
            bindings[req]=(tile,key,slot);binding_count[tile]+=1;row['bound']+=1
            binding_peak[tile]=max(binding_peak[tile],binding_count[tile])
            if binding_count[tile]>spec['outstanding_per_tile'] or row['bound']>row['expected']:raise ValueError('Return tag capacity exceeded')
        elif kind=='read_issue':
            req=e['request']
            if req not in bindings or bindings[req][1]!=key:raise ValueError('Descriptor issued without a return association')
            issued.add(req)
        elif kind=='read_deliver':
            if e['request'] not in issued or e['request'] in committed:raise ValueError('Return committed before issue or twice')
            committed.add(e['request'])
        elif kind=='return_request_commit':
            req=e['request']
            if req not in committed or bindings.get(req)!=(tile,key,slot):raise ValueError('Reply used a stale/uncommitted return association')
            del bindings[req];binding_count[tile]-=1;live[tile][key]['committed']+=1
        elif kind=='return_issue_complete':
            row=live[tile][key]
            if row['issued'] or row['bound']!=row['expected'] or row['slot']!=slot:raise ValueError('Incomplete issue context retired')
            row['issued']=True
        elif kind=='return_context_release':
            row=live[tile][key]
            if row['slot']!=slot or not row['issued'] or row['committed']!=row['expected']:raise ValueError('Return state released with data in flight')
            del live[tile][key];slots[tile].remove(slot)
    if (any(live.values()) or bindings or any(binding_count.values()) or policy['live_contexts'] or policy['live_bindings'] or
            dict(peak)!=policy['peak_contexts'] or dict(binding_peak)!=policy['binding_peak']):raise ValueError('Return tracking did not drain or peak differs')
    for tile in (t['id'] for t in spec['tiles']):
        if funding[tile]!=[expected_funding,-expected_funding]:raise ValueError('Return state was not paid inside physical SRAM')
    return dict(passed=True,return_contexts_per_cluster=policy['contexts_per_cluster'],
        binding_capacity_per_cluster=spec['outstanding_per_tile'],metadata_bytes_per_cluster=expected_funding,
        peak_contexts=dict(peak),binding_peak=dict(binding_peak),descriptors=len(issued))
