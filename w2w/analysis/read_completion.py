"""Explain observed DAG completion, without summing overlapping task waits."""


def completion_metrics(trace, result):
    rows = {t['id']: t for t in result['tasks']}
    tasks = {t.id: t for t in trace.tasks}
    if rows.keys() != tasks.keys():
        raise ValueError('Trace and replay tasks disagree')
    terminal = max(rows, key=lambda k: (rows[k]['finish_slot'], k))
    path, seen = [], set()
    key = terminal
    release_wait = 0
    while key is not None:
        if key in seen:
            raise ValueError('Cycle in observed critical path')
        seen.add(key)
        row, task = rows[key], tasks[key]
        path.append(key)
        parents = set(task.dependencies)
        if row.get('compute_predecessor') is not None:
            parents.add(row['compute_predecessor'])
        parent = max(parents, key=lambda k: (rows[k]['finish_slot'], k)) if parents else None
        previous_finish = rows[parent]['finish_slot'] if parent is not None else 0
        start = max(task.release_slot, previous_finish)
        if row['start_slot'] != start:
            raise ValueError('Unexplained task scheduling delay')
        release_wait += max(0, task.release_slot - previous_finish)
        key = parent
    path.reverse()
    memory = sum(rows[k]['reads_done_slot'] - rows[k]['start_slot'] for k in path)
    compute = sum(rows[k]['finish_slot'] - rows[k]['reads_done_slot'] for k in path)
    if memory + compute + release_wait != result['makespan_slots']:
        raise ValueError('Critical path components do not sum to makespan')
    joins = []
    for task in trace.tasks:
        if task.compute is None and len(task.dependencies) > 1:
            arrivals = [rows[k]['finish_slot'] for k in task.dependencies]
            joins.append(dict(id=task.id, arrival_span_slots=max(arrivals) - min(arrivals),
                              last_dependencies=sorted(k for k in task.dependencies
                                                       if rows[k]['finish_slot'] == max(arrivals))))
    return dict(critical_path=path, critical_read_wait_slots=memory,
                critical_compute_slots=compute, critical_release_wait_slots=release_wait,
                critical_path_sums_to_makespan=True, joins=joins)


def projected_frontier(rows):
    """Non-dominated known proxy axes only; not a complete physical-cost claim."""
    axes = ('export_lane_bits', 'endpoint_storage_bits', 'access_wire_bit_mm')
    vectors = {r['id']: (r['makespan_slots'], *(r['cost'][k] for k in axes)) for r in rows}
    return sorted(name for name, v in vectors.items() if not any(
        all(x <= y for x, y in zip(other, v)) and any(x < y for x, y in zip(other, v))
        for key, other in vectors.items() if key != name))
