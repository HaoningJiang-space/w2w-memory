"""Check range commands, physical propagation and returned credits independently."""
from collections import Counter


def audit_request_control(result):
    record=result['native'].get('request_control',{})
    if not record.get('enabled'):return dict(enabled=False)
    spec=result['spec'];stack=spec['stack'];period=spec['noc_period_ps'];native_period=spec['dram_period_ps']
    memories={m['id']:m for m in spec['memories']};gateways={g['id']:g for g in stack['gateways']}
    paths={(p['domain_id'],p['gateway_id']):p for p in stack['collection_paths']}
    expected=set();access={};sent={};arrived={};begun={};issued={};acks={};received=set()
    free=Counter();command_bytes=Counter();ack_bytes=Counter()
    edge=lambda at,p:(at+p-1)//p*p
    for e in result['events']:
        at=e['time_ps'];kind=e['kind']
        if kind=='read_issue':
            m=memories[e['memory']]
            for i in range(min(e['bytes']//32,m['banks'])):
                expected.add((e['request'],m['domain_ids'][(e['bank']+i)%m['banks']]))
        elif kind=='request_gateway_access':
            key=e['request'];g=gateways[e['gateway']]
            if key in access or at%period or at<free['access',g['id']] or e['end_ps']!=at+2*period:
                raise ValueError('Gateway control access overbooked')
            if e['arrival_ps']!=e['end_ps']+g['router_access_cycles']*period:raise ValueError('Gateway control propagation omitted')
            free['access',g['id']]=e['end_ps'];access[key]=e['arrival_ps']
        elif kind=='request_control_send':
            key=e['request'],e['domain'];path=paths[e['domain'],e['gateway']]
            if key in sent or at%period or at<free['command',e['gateway']] or at<access[e['request']]:
                raise ValueError('Command/control access or ordering violated')
            arrival=edge(e['end_ps']+(1+path['pipeline_cycles'])*period+2*native_period,native_period)
            if e['bytes']!=16 or e['end_ps']!=at+4*period or e['arrival_ps']!=arrival:
                raise ValueError('Range command width/physical timing mismatch')
            free['command',e['gateway']]=e['end_ps'];sent[key]=arrival;command_bytes[e['gateway']]+=16
        elif kind=='request_control_arrive':
            key=e['request'],e['domain']
            if key in arrived or sent.get(key)!=at:raise ValueError('Range arrived before physical command')
            arrived[key]=at
        elif kind=='domain_descriptor_begin':
            key=e['request'],e['domain']
            if key in begun or key not in arrived or at<arrived[key] or at%native_period:
                raise ValueError('Domain issued before command/clock')
            begun[key]=at
        elif kind=='domain_range_issued':
            key=e['request'],e['domain'];path=paths[e['domain'],e['gateway']]
            if key in issued or key not in begun or at<begun[key]:raise ValueError('Unowned domain range completion')
            if e['ack_ready_ps']!=edge(at+(1+path['pipeline_cycles'])*period,period):raise ValueError('ACK physical path omitted')
            issued[key]=e['ack_ready_ps']
        elif kind=='request_ack_send':
            key=e['request'],e['domain']
            if key in acks or at%period or at<issued[key] or at<free['ack',e['gateway']]:raise ValueError('ACK queue overbooked')
            if e['bytes']!=8 or e['end_ps']!=at+2*period or e['arrival_ps']!=at+4*period:raise ValueError('ACK width/CDC mismatch')
            free['ack',e['gateway']]=e['end_ps'];acks[key]=e['arrival_ps'];ack_bytes[e['gateway']]+=8
        elif kind=='request_ack_arrive':
            key=e['request'],e['domain']
            if key in received or acks.get(key)!=at:raise ValueError('Credit returned before ACK')
            received.add(key)
    if any(set(v)!=expected for v in (sent,arrived,begun,issued,acks,received)):raise ValueError('Range/ACK ledger did not complete once per domain')
    if dict(command_bytes)!=record['bytes_by_gateway'] or dict(ack_bytes)!=record['ack_bytes_by_gateway']:
        raise ValueError('Control byte ledger mismatch')
    if any(record[k] for k in ('tx_live','domain_ranges_live','ack_live')):raise ValueError('Control credits not drained')
    if any(v>record['tx_limits'][k] for k,v in record['queue_peak'].items()) or any(v>record['tx_limits'][k] for k,v in record['ack_queue_peak'].items()):
        raise ValueError('Control gateway capacity exceeded')
    if any(v>record['domain_descriptor_entries'] for v in record['domain_queue_peak'].values()):raise ValueError('Domain range buffer exceeded')
    return dict(enabled=True,passed=True,ranges=len(expected),command_bytes=sum(command_bytes.values()),ack_bytes=sum(ack_bytes.values()))
