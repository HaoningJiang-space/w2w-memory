"""Activity-based energy sensitivity, with explicit unmeasured residuals.

No default coefficient is a calibrated WSE/SeDRAM power estimate. Command-level
DRAM mode requires a separately audited command receipt; row statistics are not
substituted for commands. Buffer transfers are cost proxies, not SRAM macros.
"""
from collections import Counter, defaultdict
from fractions import Fraction
from math import isfinite


def activity(result):
    from w2w.architecture.serialization import from_record
    stack = from_record(result['spec']['stack'])
    native, net = result['native'], result['network']
    links = {c.id: c for c in stack.lateral_links}
    hops = sum(net['link_flits'].values())
    injected = sum(net['source_injected_flits'].values())
    data_bits = result['spec']['flit_bytes'] * 8
    cell_bits = data_bits + net['cell_format']['sideband_bits']
    length_flits_um = sum(links[k].length_um * n for k, n in net['link_flits'].items())
    paths = defaultdict(list)
    for path in stack.collection_paths:
        paths[path.domain_id].append(path)
    collection = Fraction(0)
    for index, domain in enumerate(stack.dram_domains):
        count = native['channel_atoms'].get(str(index), 0)
        if not count:
            continue
        if len(paths[domain.id]) != 1:
            raise ValueError('Domain aggregates do not identify a unique executed collection path')
        collection += Fraction(count * 128 * paths[domain.id][0].length_um, 1000)
    control = native['request_control']
    controls = 8 * sum(control['bytes_by_gateway'].values()) + 8 * sum(control['ack_bytes_by_gateway'].values())
    macs = weights = scales = vectors = tag = 0
    for e in result['events']:
        if e['kind'] == 'stream_compute':
            macs += e['macs'];weights += e['weight_bytes'];scales += e['scale_bytes']
        elif e['kind'] == 'compute_service':
            vectors += e['cycles']
        elif e['kind'] == 'cache_lookup_complete':
            tag += 1
    values = dict(
        dram_read_bits=native['completed_atoms'] * 128,
        hb_payload_bits=8 * sum(native['gateway_bytes'].values()),
        collection_bit_mm=float(collection),
        noc_data_bit_mm=length_flits_um * data_bits / 1000,
        noc_cell_bit_mm=length_flits_um * cell_bits / 1000,
        router_cell_bits=(hops + injected) * cell_bits,
        buffer_cell_bits=2 * (hops + injected) * cell_bits,
        sram_stream_read_bytes=weights + scales,
        sram_dma_read_bytes=sum(result['sram_read_bytes'].values()),
        sram_rx_write_bytes=sum(net['rx_write_bytes'].values()),
        macs=macs,vector_service_cycles=vectors,cache_tag_lookups=tag,
        gateway_payload_bits=8 * sum(native['gateway_bytes'].values()),
        command_ack_bits=controls,active_context_ps=sum(result['engine_context_ps'].values()))
    if values['dram_read_bits'] != values['hb_payload_bits']:
        raise ValueError('Native/HB payload activity differs')
    return dict(makespan_ps=result['makespan_ps'],drained_ps=result['drained_ps'],counts=values,
        native_read_atoms=native['completed_atoms'],dram_commands=None,
        coverage=dict(dram='Completed read atoms, not full ACT/PRE/RD/REF trace',
            hb='Useful payload/control bits, not pad toggle, clock or spare lane activity',
            noc='Actual channel cells and injection count; distance includes sideband width',
            router='One switch traversal per channel hop plus destination traversal per injected cell',
            buffer='Two transfers per router traversal, a parameterized proxy; no exact buffer toggle counter',
            sram='Observed stream/scale reads, DMA reads and receive writes; internal activation/psum banking unmeasured',
            compute='Actual MACs and observed vector service cycles; no bit-level switching',
            control='Observed range/ACK bytes, tag lookups and context-time; associative logic uncalibrated'),
        omitted=['ACT/PRE/REF/background-state energy', 'array/logic clock and power distribution',
            'internal PE activation and partial-sum SRAM accesses', 'unobserved buffer/control switching',
            'initial preload outside the measured warm interval', 'technology-specific leakage and gating'],
        contract='Link terms charge transported cells including headers/padding, not logical payload only. '
            'Buffer proxy does not include credit/control toggles. Common physical power may be swept separately. '
            'Total residual energy must cover omitted terms, unless independently supplied calibration removes them.')


def validate_coefficients(coefficients, counts):
    if set(coefficients) != set(counts):
        raise ValueError('Specify every activity coefficient; unknown/missing parameters rejected')
    for value in coefficients.values():
        if type(value) not in (int, float) or not isfinite(value) or value < 0:
            raise ValueError('Coefficients must be finite nonnegative pJ/activity-unit')
    # Data-only distance is diagnostic, not an additional path to double-charge.
    if coefficients['noc_data_bit_mm']:
        raise ValueError('Use cell distance including sideband; data distance is diagnostic only')


def evaluate(record, coefficients, *, common_power_w, residual_j):
    validate_coefficients(coefficients, record['counts'])
    for x in (common_power_w, residual_j):
        if type(x) not in (int, float) or not isfinite(x) or x < 0:
            raise ValueError('Explicit nonnegative finite power/residual required')
    terms = {k: record['counts'][k] * v * 1e-12 for k, v in coefficients.items()}
    duration = record['makespan_ps'] * 1e-12
    terms.update(common_physical_power=common_power_w * duration,unmeasured_residual=residual_j)
    energy = sum(terms.values())
    if energy <= 0:
        raise ValueError('Nonzero energy model required')
    return dict(terms_j=terms,energy_j=energy,edp_j_s=energy*duration,
        measured_energy=False,calibrated_ppa=False)


def threshold(reference, candidate):
    """Linear EDP inequality; valid for every nonnegative coefficient vector."""
    if set(reference['counts']) != set(candidate['counts']):
        raise ValueError('Activity schemas differ')
    tr = reference['makespan_ps'] * 1e-12
    tc = candidate['makespan_ps'] * 1e-12
    if min(tr, tc) <= 0:
        raise ValueError('Positive duration required')
    return dict(candidate_to_reference_time=tc/tr,
        candidate_energy_ratio_limit=tr/tc,
        activity_ratio={k:candidate['counts'][k]/v if v else None for k,v in reference['counts'].items()},
        edp_difference_coefficient={k:1e-12*(candidate['counts'][k]*tc-reference['counts'][k]*tr)
            for k in reference['counts']},
        common_power_edp_coefficient=tc*tc-tr*tr,
        residual_inequality='residual_candidate*Tc - residual_reference*Tr < '
            '-sum(activity_edp_coefficient*energy_pJ_per_unit) - common_power_W*(Tc^2-Tr^2)',
        modeled_nonnegative_coefficient_dominance=all(candidate['counts'][k]*tc <= v*tr for k,v in reference['counts'].items()),
        contract='Dominance applies to covered activities and common coefficients only. '
            'It is not a bound on unmeasured residuals or calibrated total energy. '
            'Preload is excluded on both sides; no dynamic migration or free initial load claim.')


def edp_range(reference, candidate, coefficient_ranges, *, power_range, residual_reference_range, residual_candidate_range):
    """Exact extrema of a linear EDP difference over a declared parameter box."""
    if set(coefficient_ranges) != set(reference['counts']):
        raise ValueError('Specify every coefficient range')
    def bounds(pair):
        if (len(pair)!=2 or any(type(v) not in (int,float) or not isfinite(v) or v<0 for v in pair)
                or pair[0]>pair[1]):raise ValueError('Finite ordered nonnegative ranges required')
        return pair
    for pair in coefficient_ranges.values():bounds(pair)
    if any(coefficient_ranges['noc_data_bit_mm']):raise ValueError('Data-only diagnostic is not double-charged')
    t=threshold(reference,candidate);tr=reference['makespan_ps']*1e-12;tc=candidate['makespan_ps']*1e-12
    terms=[(t['edp_difference_coefficient'][k],bounds(v)) for k,v in coefficient_ranges.items()]
    terms += [(t['common_power_edp_coefficient'],bounds(power_range)),
              (-tr,bounds(residual_reference_range)),(tc,bounds(residual_candidate_range))]
    lo=sum(min(a*b[0],a*b[1]) for a,b in terms);hi=sum(max(a*b[0],a*b[1]) for a,b in terms)
    return dict(edp_difference_min_j_s=lo,edp_difference_max_j_s=hi,
        candidate_better_for_entire_declared_box=hi<0,
        candidate_worse_for_entire_declared_box=lo>0,calibrated=False,
        contract='A declared box is a sensitivity scenario, not an empirical confidence interval. '
            'Unbounded residuals cannot establish total-energy ordering.')


def command_energy(record, receipt, coefficients):
    """Optional separate array-command term; never mix with per-read-bit energy."""
    if (not receipt.get('passed') or receipt.get('read_atoms') != record['native_read_atoms']
            or not record.get('raw_result_sha256') or receipt.get('raw_result_sha256') != record['raw_result_sha256']
            or not receipt.get('trace_sha256')):
        raise ValueError('Command receipt must bind audited trace and raw result')
    totals = Counter()
    for channel in receipt['channels'].values():
        totals.update(channel['commands'])
    allowed = {'ACT', 'PREpb', 'PREab', 'RD', 'REFab'}
    if set(totals)-allowed or set(coefficients) != allowed or totals['RD'] != record['native_read_atoms']:
        raise ValueError('Unsupported or incomplete read-only command energy inputs')
    if any(type(v) not in (int, float) or not isfinite(v) or v < 0 for v in coefficients.values()):
        raise ValueError('Finite nonnegative command pJ required')
    return {k:totals[k]*coefficients[k]*1e-12 for k in allowed}
