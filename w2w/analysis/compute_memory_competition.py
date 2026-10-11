"""Read-only clock accounting; observations are not counterfactual stall savings."""
from bisect import bisect_left
from collections import Counter, defaultdict
from .ffn_stages import stages


def clocks(begin, end, period):
    """Global clock edges in the half-open interval [begin, end)."""
    return max(0, (end + period - 1) // period - (begin + period - 1) // period)


class Occupancy:
    def __init__(self, changes, capacity):
        if type(capacity) is not int or capacity < 1:
            raise ValueError('Positive finite capacity required')
        self.full = []
        self.area = 0
        live = set()
        last = 0
        # Stable event order preserves same-timestamp release/acquire semantics.
        for at, key, acquire in changes:
            if at < last:
                raise ValueError('Nonmonotonic ownership events')
            if len(live) == capacity and at > last:
                if self.full and self.full[-1][1] == last:
                    self.full[-1] = (self.full[-1][0], at)
                else:
                    self.full.append((last, at))
            self.area += (at - last) * len(live)
            if acquire:
                if key in live or len(live) >= capacity:
                    raise ValueError('Duplicate ownership or capacity exceeded')
                live.add(key)
            else:
                if key not in live:
                    raise ValueError('Release without ownership')
                live.remove(key)
            last = at
        if live:
            raise ValueError('Ownership did not drain')
        self.ends = [b for _, b in self.full]

    def blocked_clocks(self, begin, end, period):
        n = 0
        for a, b in self.full[bisect_left(self.ends, begin):]:
            if a >= end:
                break
            n += clocks(max(a, begin), min(b, end), period)
        return n


def competition(result):
    if result.get('compute_epoch') or result.get('interactive_compute'):
        raise ValueError('This reader requires ordinary full compute events')
    tasks = {t['id']: t for t in result['graph']['tasks']}
    periods = {c['id']: c['profile']['period_ps'] for c in result['spec']['stack']['compute_clusters']}
    changes, fetch, grants = defaultdict(list), defaultdict(list), defaultdict(list)
    for e in result['events']:
        kind, key = e['kind'], e.get('task')
        if key not in tasks:
            continue
        tile, at = tasks[key]['tile'], e['time_ps']
        if kind in ('task_start', 'task_finish'):
            changes[tile].append((at, key, kind == 'task_start'))
        elif kind in ('fetch_context_acquire', 'fetch_context_release'):
            fetch[tile].append((at, key, kind == 'fetch_context_acquire'))
        elif kind in ('stream_compute', 'compute_service'):
            if at % periods[tile] or grants[tile] and grants[tile][-1] == at:
                raise ValueError('Shared MAC/read grant duplicated or off clock')
            grants[tile].append(at)
    contexts = {t: Occupancy(v, result['compute_execution']['contexts_per_cluster']) for t, v in changes.items()}
    fetches = {t: Occupancy(v, result['fetch_execution']['contexts_per_cluster']) for t, v in fetch.items()}
    shared = Counter()
    def observe(key, label, begin, end, count):
        if label != 'ready':
            return
        ticks = grants[tasks[key]['tile']]
        competing = bisect_left(ticks, end) - bisect_left(ticks, begin)
        if competing != count:
            raise ValueError('Ready context waited without another shared grant; unsupported policy/evidence')
        shared[key] += competing
    stage = stages(result, observe)
    clusters, phases = {}, {}
    for key, row in stage['tasks'].items():
        m, tile = row['milestones'], row['tile']
        period = periods[tile]
        start_ready = max(m['allocate'], m.get('input_ready', 0), m.get('scale_ready', 0), m['dependency_ready'])
        ctx_wait = contexts[tile].blocked_clocks(start_ready, m['start'], period)
        fetch_wait = fetches[tile].blocked_clocks(m['dependency_ready'], m['allocate'], period) if tasks[key]['reads'] else 0
        # Count grants to OTHER tasks while this started context is service-ready.
        # ff_n_stages partitions those opportunities exactly; subtract ungranted
        # cluster clocks from them. An idle cluster cannot block a ready context
        # under the ordinary work-conserving scheduler.
        clocks_active = clocks(m['start'], m['finish'], period)
        ticks = grants[tile]
        issued = bisect_left(ticks, m['finish']) - bisect_left(ticks, m['start'])
        idle = clocks_active - issued
        shared_wait = shared[key]
        if shared_wait != row['ready_service_wait_cycles']:
            raise ValueError('Shared grant waiting differs from sparse stage partition')
        if idle < row['operand_wait_cycles'] - (issued - row['busy_cycles']):
            raise ValueError('Inconsistent cluster/context opportunities')
        # A clock that is ready but ungranted must have a different grant. The
        # sparse stage partition and work-conserving policy establish this; keep
        # clock-alignment residual separate rather than calling it contention.
        row.update(start_eligible_ps=start_ready,
            compute_context_full_before_start_ps=ctx_wait * period,
            pre_start_other_or_alignment_ps=row['start_after_required_inputs_ps'] - ctx_wait * period,
            fetch_full_before_admit_ps=fetch_wait * period,
            fetch_admission_other_or_alignment_ps=row['dependency_to_allocate_ps'] - fetch_wait * period,
            shared_grant_wait_ps=shared_wait * period,
            cluster_idle_clocks_during_context=idle)
        if min(row['pre_start_other_or_alignment_ps'], row['fetch_admission_other_or_alignment_ps']) < 0:
            raise ValueError('Capacity waiting exceeds observed admission interval')
        for target, label in ((clusters, tile), (phases, row['phase'])):
            a = target.setdefault(label, Counter())
            a['tasks'] += 1
            for field in ('busy_ps', 'context_ps', 'operand_wait_ps', 'shared_grant_wait_ps',
                          'compute_context_full_before_start_ps', 'fetch_full_before_admit_ps',
                          'fetch_admission_other_or_alignment_ps', 'pre_start_other_or_alignment_ps'):
                a[field] += row[field]
    for tile, ctx in contexts.items():
        if ctx.area != result['engine_context_ps'][tile] or clusters[tile]['busy_ps'] != result['compute_busy_ps'][tile]:
            raise ValueError('Reconstructed service/ownership differs from execution ledger')
        clusters[tile]['context_full_wall_ps'] = sum(b - a for a, b in ctx.full)
        clusters[tile]['fetch_full_wall_ps'] = sum(b - a for a, b in fetches.get(tile, Occupancy([], 1)).full)
    chain = stage['latest_finishing_predecessor_chain'][-20:]
    blocks = {t['task'].rsplit('/', 1)[0] for t in chain if t['phase'] in ('gate', 'up', 'down', 'activation', 'accumulate')}
    selected = {k: v for k, v in stage['tasks'].items() if k.rsplit('/', 1)[0] in blocks}
    return dict(clusters={k: dict(v) for k, v in clusters.items()}, phases={k: dict(v) for k, v in phases.items()},
        tail_blocks=selected, projection_pairs={k: v for k, v in stage['projection_pairs'].items() if k in blocks},
        contract='Integer-ps reconstruction from full ordinary events. Context clocks partition into service, '
                 'missing consumable contiguous operand, and ready but another shared grant. Pre-start capacity '
                 'counts use half-open occupancy intervals and clock edges; same-tick ordering/alignment remains '
                 'in the residual. Dependency-to-allocation may also include SRAM/cache/tag availability. '
                 'Overlapping per-task/context counters are not additive wall-clock stalls or removable latency. '
                 'The latest-finishing dependency chain omits implicit shared-resource edges; no global causal attribution.')
