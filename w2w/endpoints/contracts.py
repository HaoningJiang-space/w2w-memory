"""Endpoint capacities as domain values; no wafer solver dependency."""
from w2w.domain.endpoint import EndpointEnvelope, LinearLimit


def scalar_contract(output_limits, route_outputs, memories, banks, bank_bw,
                    contract='elastic', alpha=1., efficiency=1.):
    """Historical scalar contract, expressed without inheritance or LP code."""
    if contract not in ('elastic', 'fixed_share', 'direct', 'buffered_envelope'):
        raise ValueError('Unknown endpoint contract')
    if not 0 < alpha <= 1 or not 0 < efficiency <= 1:
        raise ValueError('Invalid contract')
    caps = {}
    for label, physical_capacity, degree in output_limits:
        peak = min(alpha, 1 / degree) if contract == 'fixed_share' else alpha
        caps[label] = min(physical_capacity, peak * bank_bw)
    limits = []
    if contract in ('direct', 'buffered_envelope'):
        terms = {b: [] for b in range(memories * banks)}
        for key, output in route_outputs:
            peak = caps[output] if contract == 'direct' else bank_bw
            terms[key[1]].append((key, 1 / peak))
        for m in range(memories):
            for b in range(banks):
                limits.append(LinearLimit(('endpoint_time', m, b), tuple(terms[m * banks + b]), efficiency))
    return EndpointEnvelope(tuple(caps.items()), limits=tuple(limits))


def role_envelope(design):
    caps = []
    for m in range(len(design.geometry.memory_xy)):
        for b, ports in enumerate(design.exposure.mask):
            for p in ports:
                capacity = design.endpoint.widths[p] / design.endpoint.word_bits * design.exposure.bank_bw
                if p in design.endpoint.shared_fifo_ports and p != design.shared_directions[m]:
                    capacity = 0.
                caps.append((('bank_output', m, b, p), capacity))
    return EndpointEnvelope(tuple(caps), scope='Role width fluid upper bound; finite execution is separate')
