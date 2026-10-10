"""Necessary work bounds and explicitly conditional ideal service schedules.

These are not execution-time predictions or independent additive stall terms.
"""
from collections import Counter, defaultdict
from fractions import Fraction
from math import ceil
from w2w.architecture.serialization import from_record


def matrix_pipeline(*, matrix_bytes=524416, gateway_bytes_per_ns=32,
                    slices=1, independent_services=2, down_prefetch=False):
    if any(type(v) is not int or v < 1 for v in
           (matrix_bytes, gateway_bytes_per_ns, slices, independent_services)):
        raise ValueError('Positive integer matrix/service budgets required')
    if independent_services not in (2, 3): raise ValueError('Specify two or three independent services')
    service = Fraction(matrix_bytes * 1000, gateway_bytes_per_ns)
    work = service * (2 if independent_services == 2 else 1)
    # Down weight fetch is independent of H; arithmetic still requires H.
    ideal = work if down_prefetch or independent_services == 2 else service * Fraction(slices+1, slices)
    return dict(payload_work_bound_ps=ceil(work), ideal_schedule_ps=ceil(ideal),
        contract='Equal matrices, cold payload only, uncongested dedicated services; arithmetic/scale/control/transport costs omitted. '
                 'Two services assign Gate+Down to A and Up to B. Three services dedicate one per matrix. '
                 'Without prefetch, Down slice fetching starts after its H exists. With prefetch and sufficient storage/association, '
                 'all weight fetching can precede H; this removes the assumed two-stage fetch barrier even for a whole matrix. '
                 'A dedicated-service schedule is not a whole-wafer bandwidth allocation or a universal latency bound.')


def service_bounds(result):
    spec = result['spec']; stack = from_record(spec['stack'])
    gateways = {g.id:g for g in (*stack.gateways, *stack.external_ports)}
    memories = {m['id']:m for m in spec['memories']}
    domains = {d.id:d for d in stack.dram_domains}
    duration = result['makespan_ps']; period = spec['noc_period_ps']
    rates = {key:Fraction(g.data_bytes_per_cycle, period) for key,g in gateways.items()}
    gateway_bytes = Counter(); task_gateway = defaultdict(Counter); task_domain = defaultdict(Counter)
    for event in result['events']:
        if event['kind'] != 'read_issue': continue
        memory = memories[event['memory']]; n = event['bytes']//32
        gateway_bytes[memory['gateway_id']] += event['bytes']
        task_gateway[event['task']][memory['gateway_id']] += event['bytes']
        for bank, domain in enumerate(memory['domain_ids']):
            first = (bank-event['bank']) % memory['banks']
            count = max(0, (n-first+memory['banks']-1)//memory['banks'])
            task_domain[event['task']][domain] += 2*count
    if dict(gateway_bytes) != {k:v for k,v in result['native']['gateway_bytes'].items() if v}:
        raise ValueError('Issued byte work differs from completed gateway work')
    gateway_bounds = {key:ceil(Fraction(n)/rates[key]) for key,n in gateway_bytes.items()}
    total = sum(gateway_bytes.values()); capacity = sum(rates.values(), Fraction(0))
    global_gateway = ceil(Fraction(total)/capacity) if total else 0
    domain_atoms = Counter()
    for values in task_domain.values(): domain_atoms.update(values)
    if sum(domain_atoms.values()) != result['native']['completed_atoms']:
        raise ValueError('Physical atom service differs from issued descriptors')
    domain_bounds = {d:n*domains[d].period_ps for d,n in domain_atoms.items()}
    hb_bounds = {}
    for port in stack.vertical_ports:
        amount = sum(domain_atoms[d]*16 for d in port.domain_ids)
        hb_bounds[port.id] = ceil(Fraction(amount*8*port.period_ps, port.data_bits))
    channel_bounds = {}; byte_um = 0
    for link in stack.lateral_links:
        cells = result['network']['link_flits'].get(link.id,0)
        lane_bytes = cells*spec['flit_bytes']
        channel_bounds[link.id] = ceil(Fraction(lane_bytes*8*link.period_ps,link.data_bits))
        byte_um += lane_bytes*link.length_um
    rx_bounds = {tile:ceil(Fraction(n*period,spec['rx_write_bytes_per_cycle']))
                 for tile,n in result['network']['rx_write_bytes'].items()}
    tasks = {t['id']:t for t in result['graph']['tasks']}
    parents = {k:set() for k in tasks}; following = defaultdict(set)
    for edge in (*result['graph']['data'], *result['graph']['control']):
        parents[edge['consumer']].add(edge['producer']); following[edge['producer']].add(edge['consumer'])
    remaining = {k:len(v) for k,v in parents.items()}; ready = [k for k,n in remaining.items() if not n]
    compute_work = Counter(); finish = {}; fetch_hold = Counter(); fetch_task = {}
    tile_period = {t['id']:t['compute_period_ps'] for t in spec['tiles']}
    while ready:
        key = ready.pop(); task = tasks[key]; stream = task['stream']; clock = tile_period[task['tile']]
        cycles = (max(ceil(Fraction(stream['weight_data_bytes'],stream['weight_read_bytes_per_cycle'])),
                      ceil(Fraction(stream['macs'],stream['macs_per_cycle'])))+1 if stream else task['compute_cycles'])
        service = cycles*clock; compute_work[task['tile']] += service
        finish[key] = max(task['release_ps'], max((finish[p] for p in parents[key]), default=0))+service
        hold = max([ceil(Fraction(n)/rates[g]) for g,n in task_gateway[key].items()] +
                   [n*domains[d].period_ps for d,n in task_domain[key].items()] +
                   [ceil(Fraction(sum(task_gateway[key].values())*period,spec['rx_write_bytes_per_cycle']))])
        fetch_task[key] = hold; fetch_hold[task['tile']] += hold
        for child in following[key]:
            remaining[child] -= 1
            if not remaining[child]: ready.append(child)
    if len(finish) != len(tasks): raise ValueError('Cyclic dependency record')
    slots = result.get('fetch_execution',{}).get('contexts_per_cluster',0)
    slot_bounds = {tile:ceil(Fraction(work,slots)) for tile,work in fetch_hold.items()} if slots else {}
    terms = dict(global_gateway_payload_ps=global_gateway,
        fixed_gateway_assignment_ps=max(gateway_bounds.values(),default=0),
        native_data_bus_ps=max(domain_bounds.values(),default=0),
        vertical_data_lane_ps=max(hb_bounds.values(),default=0),
        executed_channel_data_lane_ps=max(channel_bounds.values(),default=0),
        receiver_write_ps=max(rx_bounds.values(),default=0),
        shared_compute_ps=max(compute_work.values(),default=0),
        arithmetic_dependency_ps=max(finish.values(),default=0),
        finite_fetch_ownership_ps=max(slot_bounds.values(),default=0))
    necessary = max(terms.values())
    if necessary > duration: raise ValueError('Necessary service exceeds observed makespan')
    return dict(schema='w2w.service-bounds.v1', native_bytes=total, makespan_ps=duration,
        terms=terms, necessary_bound_ps=necessary, gateway_payload_bounds_ps=gateway_bounds,
        domain_data_bus_bounds_ps=domain_bounds, vertical_lane_bounds_ps=hb_bounds,
        channel_data_lane_bounds_ps=channel_bounds, receiver_write_bounds_ps=rx_bounds,
        arithmetic_earliest_finish_ps=finish, shared_compute_bounds_ps=dict(compute_work),
        minimum_fetch_hold_ps=fetch_task, finite_slot_work_bounds_ps=slot_bounds,
        executed_data_lane_byte_um=byte_um,
        contract='Max of necessary work bounds, never their sum. Uses actual cold/miss descriptors and executed traffic; '
                 'cached matrices contribute no native byte work. Domain buses omit ACT/PRE/REF inefficiency; '
                 'arithmetic-only DAG omits data service and implicit contention; finite slots bound total minimum hold work, '
                 'not the actual arbitration schedule. Data-lane distance is an activity proxy, not measured energy/PPA.')
