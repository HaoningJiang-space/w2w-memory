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


def audit_study(summary, folder):
    """Reconcile archived counters/hashes and expose initial partner contention."""
    import gzip
    from hashlib import sha256
    import json
    from pathlib import Path
    from w2w.workloads.read_trace import digest

    records = []
    total = 0
    for artifact, compact in zip(summary['artifacts'], summary['cases'], strict=True):
        raw = (Path(folder) / artifact['path']).read_bytes()
        if sha256(raw).hexdigest() != artifact['sha256']:
            raise ValueError('Study artifact hash mismatch')
        case = json.loads(gzip.decompress(raw))
        if digest(case['trace']) != artifact['trace_sha256']:
            raise ValueError('Trace hash mismatch')
        logical_bytes = sum(r['size_bytes'] for t in case['trace']['tasks'] for r in t['reads'])
        contexts = []
        for row, small in zip(case['results'], compact['rows'], strict=True):
            if any(row[k] != v for k, v in small.items()):
                raise ValueError('Summary and raw replay disagree')
            if (digest(row['design']) != row['design_sha256']
                    or digest(row['residence']) != row['residence_sha256']):
                raise ValueError('Design or residence hash mismatch')
            counts = row['audit']
            if (any(counts[k] != logical_bytes // 32 for k in
                    ('issued_words', 'admitted_words', 'transmitted_words', 'delivered_words'))
                    or counts['sent_bits'] != logical_bytes * 8
                    or sum(r['sent_bits'] for r in row['routes']) != logical_bytes * 8
                    or sum(r['received_words'] for r in row['routes']) != logical_bytes // 32
                    or sum(row['native_words_by_bank'].values()) != logical_bytes // 32):
                raise ValueError('Independent aggregate conservation failure')
            total += counts['delivered_words']
            shares = row['design']['layout']['shares']
            owners = [{c for c, values in enumerate(shares) if values[b]} for b in range(len(shares[0]))]
            stages = sorted({t['id'].split('/')[0] for t in row['tasks'] if t['logical_bytes']})
            for stage in stages:
                tasks = [t for t in row['tasks'] if t['id'].split('/')[0] == stage and t['logical_bytes']]
                active = {t['compute'] for t in tasks}
                private, busy = [], []
                for task in tasks:
                    c = task['compute']
                    banks = [int(b) for b in task['bank_bytes']]
                    neighbors = set().union(*(owners[b] for b in banks)) - {c}
                    if any(owners[b] == {c} for b in banks):
                        private.append(c)
                    if neighbors & active:
                        busy.append(c)
                contexts.append(dict(design=row['id'], stage=stage, active=sorted(active),
                                     required_private_bank_clients=private,
                                     initially_busy_sharing_competitor_clients=busy))
        records.append(dict(case=case['case'], control=case['control'], contexts=contexts))
    # Independent closed-form Home oracles for these registered DAGs and settings.
    expected_home = dict(single=88, dispersed9=88, clustered9=88, full36=88,
                         moving9=352, straggler9=354, short9=4)
    for case in summary['cases']:
        if case['control'] == 'base' and case['rows'][0]['makespan_slots'] != expected_home[case['case']]:
            raise ValueError('Analytical Private completion oracle failed')
    return dict(verified=True, delivered_words_across_replays=total, analytical_home_oracles=expected_home,
                contexts=records, scope='Independent archive/counter/Private-time checks; contexts describe '
                                       'initial stage activity, not persistent contention or RTL equivalence')


def render_study(summary, output):
    """Export finite-workload figures; never combine model time with ASIC area."""
    from pathlib import Path
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    main = [c for c in summary['cases'] if c['control'] == 'base']
    names = [r['id'] for r in main[0]['rows']]
    # Dup/config have identical times; show each performance curve once.
    selected = [names[i] for i in (0, 1, 2, 5, 6)]
    labels = ['Private', 'k2 direct', 'k3 wide', 'Paired A cfg', 'Paired B cfg']
    times = [[next(r['makespan_slots'] for r in c['rows'] if r['id'] == k)
              for k in selected] for c in main]
    ratio = np.array(times) / np.array(times)[:, :1]
    fig, ax = plt.subplots(figsize=(8.5, 4.8), layout='constrained')
    im = ax.imshow(ratio, cmap='RdYlBu_r', vmin=.5, vmax=1.2, aspect='auto')
    ax.set_xticks(range(len(labels)), labels)
    ax.set_yticks(range(len(main)), [c['case'] for c in main])
    for i, row in enumerate(ratio):
        for j, value in enumerate(row):
            ax.text(j, i, f'{value:.3f}\n({times[i][j]} slots)', ha='center', va='center', fontsize=9)
    ax.set_title('Finite task completion / Private (lower is better)\nSynthetic H/plus; fixed residence; 128 outstanding words/C')
    fig.colorbar(im, ax=ax, label='Normalized makespan', shrink=.85)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for suffix in ('svg', 'png'):
        fig.savefig(output / f'completion.{suffix}', dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), layout='constrained')
    for ax, case in zip(axes, ('dispersed9', 'clustered9', 'full36')):
        data = [next(c for c in summary['cases'] if c['case'] == case and c['control'] == control)
                for control in ('base', 'credits512')]
        for label, key in zip(labels, selected):
            values = [next(r['makespan_slots'] for r in c['rows'] if r['id'] == key) for c in data]
            ax.plot((0, 1), values, marker='o', label=label)
        ax.set_xticks((0, 1), ('128 words', '512 words'))
        ax.set_xlabel('Outstanding words per compute')
        ax.set_title(case)
        ax.grid(alpha=.2)
    axes[0].set_ylabel('Makespan (native slots)')
    axes[-1].legend(fontsize=8)
    fig.suptitle('Credit control: same issue, native, endpoint and RX contracts')
    for suffix in ('svg', 'png'):
        fig.savefig(output / f'credits.{suffix}', dpi=180)
    plt.close(fig)


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    summary = json.loads(Path(args.summary).read_text())
    audit = audit_study(summary, Path(args.summary).parent)
    render_study(summary, args.output)
    (Path(args.output) / 'audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    print('VERIFIED archive, counters and Private analytical completion;',
          audit['delivered_words_across_replays'], 'delivered model words')
