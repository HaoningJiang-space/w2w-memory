"""Independent conservation across the native, vertical and execution ledgers."""
from collections import Counter
from .system_execution import audit_system_result


def audit_vertical_result(result):
    audit=audit_system_result(result)
    stack=result['spec']['stack'];native=result['native']
    domains={d['id']:d for d in stack['dram_domains']}
    expected=sum(r['size_bytes'] for t in result['graph']['tasks'] for r in t['reads'])
    if native['physical_domain_count']!=len(domains) or native['physical_capacity_bytes']!=sum(d['capacity_bytes'] for d in domains.values()):
        raise ValueError('Native physical service/capacity was duplicated')
    if (native['completed_atoms']*16!=expected or sum(native['gateway_bytes'].values())!=expected
            or native['pending'] or native['upstream_pending'] or native['reservations_live']):
        raise ValueError('Native/vertical bytes or reservations did not drain')
    channel_domains=list(domains.values())
    for key,peak in native['reservation_peak_atoms'].items():
        if peak>channel_domains[int(key)]['return_atoms']:raise ValueError('Native return capacity exceeded')
    gateways={g['id']:g for g in (*stack['gateways'],*stack['external_ports'])}
    for key,peak in native['gateway_queue_peak_bytes'].items():
        if peak>gateways[key]['staging_bytes']:raise ValueError('Gateway staging capacity exceeded')
    pools={m['mc_pool_id']:m['transaction_slots'] for m in result['spec']['memories']}
    if any(p>pools[k] for k,p in result['mc_pool_peak'].items()):raise ValueError('Shared MC pool was replicated')
    return dict(**audit,physical_domains=len(domains),native_bytes=expected,
        gateway_bytes=sum(native['gateway_bytes'].values()),physical_collection_charged=bool(stack['collection_paths']),
        native_and_gateway_reservations_drained=True)
