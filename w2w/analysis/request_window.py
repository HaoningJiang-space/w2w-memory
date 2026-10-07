"""Necessary credit and finite completion bounds for the existing read replay.

These are optimistic bounds, not a DRAM/RTL timing model or sufficient buffers.
Request slots count from issue (inclusive) to delivery (exclusive).
"""
from dataclasses import asdict
from fractions import Fraction

from w2w.service.read_replay import design_record
from w2w.workloads.read_residency import ReadResidency
from w2w.workloads.read_trace import digest, integer


def ceil_div(a, b):
    return (a + b - 1) // b


def window_certificate(design, trace, config):
    residence = ReadResidency(design, trace)
    spec = design.endpoint
    rows = []
    for task in trace.tasks:
        routes = []
        for bank, byte_count in residence.task_bytes(task).items():
            port = residence.evaluator.ports[task.compute, bank]
            width = spec.widths[port]
            words = byte_count // trace.word_bytes
            # Even a word beginning at a beat boundary needs ceil(W/w) slots.
            # Queuing, native unavailability and RX stalls can only increase it.
            lifetime = (config.request_latency_slots + config.native_latency_slots
                        + ceil_div(spec.word_bits, width) + config.link_latency_slots)
            route_time = (config.request_latency_slots + config.native_latency_slots
                          + ceil_div(words * spec.word_bits, width) + config.link_latency_slots)
            native_time = (config.request_latency_slots + config.native_latency_slots
                           + words + config.link_latency_slots)
            routes.append(dict(bank=bank, port=port, words=words, width_bits=width,
                               minimum_word_lifetime_slots=lifetime,
                               required_credit_word_slots=words * lifetime,
                               independent_read_slots=max(route_time, native_time)))
        words = sum(r['words'] for r in routes)
        independent = max((r['independent_read_slots'] for r in routes), default=0)
        if words:
            last_issue = ceil_div(words, config.request_words_per_compute_slot) - 1
            independent = max(independent, last_issue + min(
                r['minimum_word_lifetime_slots'] for r in routes))
        rows.append(dict(id=task.id, compute=task.compute, dependencies=list(task.dependencies),
                         release_slot=task.release_slot, compute_slots=task.compute_slots,
                         words=words, routes=routes,
                         required_credit_word_slots=sum(r['required_credit_word_slots'] for r in routes),
                         independent_read_slots=independent))
    contract = asdict(config)
    del contract['outstanding_words_per_compute']
    return dict(schema='w2w.request-window-certificate.v1', trace_sha256=trace.sha256,
                design_sha256=digest(design_record(design)), residence_sha256=residence.sha256,
                fixed_config=contract, tasks=rows,
                scope='Necessary bounds for frozen word/bit-budget replay; ignores competing tasks, '
                      'native unavailable slots, queue stalls and beat phase; not sufficient sizing')


def completion_lower_bound(certificate, window=None):
    """DAG bound; ignoring compute serialization only makes it more optimistic."""
    if window is not None:
        integer(window, 'request window', 1)
    pending = {t['id']: t for t in certificate['tasks']}
    finished = {}
    while pending:
        ready = [t for t in pending.values() if all(p in finished for p in t['dependencies'])]
        if not ready:
            raise ValueError('Invalid certificate DAG')
        for task in ready:
            start = max((task['release_slot'], *(finished[p] for p in task['dependencies'])))
            read = task['independent_read_slots']
            if window is not None:
                read = max(read, ceil_div(task['required_credit_word_slots'], window))
            finished[task['id']] = start + read + task['compute_slots']
            del pending[task['id']]
    return max(finished.values())


def rate_window_lower_bound(task, words_per_slot):
    """Necessary *steady* window for a supplied rate and this exact byte mix."""
    rate = Fraction(words_per_slot)
    if not task['words'] or rate <= 0:
        raise ValueError('Positive rate and nonempty read required')
    occupied = rate * task['required_credit_word_slots'] / task['words']
    return ceil_div(occupied.numerator, occupied.denominator)


def check_bound(certificate, row):
    """Check every observed task and total time, not only the winning task."""
    for key in ('trace_sha256', 'design_sha256', 'residence_sha256'):
        if certificate[key] != row[key]:
            raise ValueError('Certificate/replay identity mismatch: ' + key)
    config = {k: v for k, v in row['config'].items() if k != 'outstanding_words_per_compute'}
    if digest(config) != digest(certificate['fixed_config']):
        raise ValueError('Certificate/replay fixed configuration mismatch')
    observed = {t['id']: t for t in row['tasks']}
    if observed.keys() != {t['id'] for t in certificate['tasks']}:
        raise ValueError('Certificate/replay task mismatch')
    window = row['config']['outstanding_words_per_compute']
    for task in certificate['tasks']:
        lower = max(task['independent_read_slots'],
                    ceil_div(task['required_credit_word_slots'], window))
        if observed[task['id']]['read_wait_slots'] < lower:
            raise ValueError('Observed read violates necessary bound')
    if row['makespan_slots'] < completion_lower_bound(certificate, window):
        raise ValueError('Observed completion violates necessary bound')
    return True


def scan_minimum_window(certificate, deadline, maximum, evaluate):
    """Exhaust the necessary interval; never assume replay time is monotone.

    evaluate(window) returns makespan and may cache previously checked windows.
    Smaller windows are excluded by the bound or individually executed.
    """
    integer(deadline, 'deadline')
    integer(maximum, 'maximum window', 1)
    independent = completion_lower_bound(certificate)
    if independent > deadline:
        return dict(deadline_slots=deadline, status='impossible_by_resource_bound',
                    independent_completion_lower_bound=independent, minimum_window=None,
                    first_not_excluded_by_bound=None, evaluated_windows=[])
    first = next((n for n in range(1, maximum + 1)
                  if completion_lower_bound(certificate, n) <= deadline), maximum + 1)
    checked = []
    for window in range(first, maximum + 1):
        time = evaluate(window)
        checked.append(window)
        if time <= deadline:
            return dict(deadline_slots=deadline, status='minimum_certified', minimum_window=window,
                        first_not_excluded_by_bound=first, evaluated_windows=checked,
                        achieved_makespan_slots=time,
                        independent_completion_lower_bound=independent)
    return dict(deadline_slots=deadline, status='unattained_within_registered_window_range',
                minimum_window=None, first_not_excluded_by_bound=first, evaluated_windows=checked,
                independent_completion_lower_bound=independent)


def request_cost_frontier(rows):
    """Keep request entries as an extra dimension; do not invent bit/area weights."""
    axes = ('export_lane_bits', 'endpoint_storage_bits', 'access_wire_bit_mm')
    vectors = {r['id']: (r['makespan_slots'], *(r['cost'][k] for k in axes),
                        r['config']['outstanding_words_per_compute']) for r in rows}
    return sorted(k for k, value in vectors.items() if not any(
        all(a <= b for a, b in zip(other, value)) and any(a < b for a, b in zip(other, value))
        for name, other in vectors.items() if name != k))


def audit_archive(folder):
    """Read back every raw row and verify exclusion/witness coverage independently."""
    import gzip
    from hashlib import sha256
    import json
    from pathlib import Path

    folder = Path(folder)
    summary = json.loads((folder / 'summary.json').read_text())
    for artifact in summary['artifacts']:
        raw = (folder / artifact['path']).read_bytes()
        if sha256(raw).hexdigest() != artifact['sha256'] or len(raw) != artifact['bytes']:
            raise ValueError('Result artifact hash/length mismatch')
    certificates = {(r['case'], r['label']): r['certificate'] for r in
                    json.loads(gzip.decompress((folder / 'certificates.json.gz').read_bytes()))}
    rows = {}
    delivered = 0
    with gzip.open(folder / 'replays.jsonl.gz', 'rb') as stream:
        for index, (line, compact) in enumerate(zip(stream, summary['replays'], strict=True)):
            if compact['sequence'] != index or sha256(line).hexdigest() != compact['uncompressed_record_sha256']:
                raise ValueError('Raw replay sequence/hash mismatch')
            record = json.loads(line)
            row = record['replay']
            key = (record['case'], record['label'], record['window'])
            if key in rows or key != (compact['case'], compact['label'], compact['window']):
                raise ValueError('Duplicate/mismatched replay key')
            for field in ('id', 'trace_sha256', 'design_sha256', 'residence_sha256', 'makespan_slots',
                          'delivery_sha256', 'audit', 'stalls', 'completion', 'request_cost'):
                if row[field] != compact[field]:
                    raise ValueError('Raw/summary mismatch: ' + field)
            if digest(row['design']) != row['design_sha256'] or digest(row['residence']) != row['residence_sha256']:
                raise ValueError('Raw design/residence hash mismatch')
            check_bound(certificates[key[:2]], row)
            if compact['completion_lower_bound'] != completion_lower_bound(certificates[key[:2]], key[2]):
                raise ValueError('Recorded lower bound mismatch')
            expected = sum(t['logical_bytes'] for t in row['tasks']) // 32
            if (any(row['audit'][k] != expected for k in
                    ('issued_words', 'admitted_words', 'transmitted_words', 'delivered_words'))
                    or row['audit']['sent_bits'] != 256 * expected
                    or sum(r['received_words'] for r in row['routes']) != expected
                    or sum(row['native_words_by_bank'].values()) != expected
                    or sum(r['sent_bits'] for r in row['routes']) != expected * 256):
                raise ValueError('Independent word/bit conservation failure')
            delivered += expected
            rows[key] = {k: v for k, v in row.items() if k not in ('design', 'residence', 'composition')}
    for result in summary['searches']:
        cert = certificates[result['case'], result['label']]
        target = result['deadline_slots']
        if result['status'] == 'impossible_by_resource_bound':
            if completion_lower_bound(cert) <= target or result['evaluated_windows']:
                raise ValueError('Invalid resource-impossibility certificate')
            continue
        first = result['first_not_excluded_by_bound']
        if any(completion_lower_bound(cert, n) <= target for n in range(1, first)):
            raise ValueError('Necessary bound did not exclude skipped windows')
        if result['status'] == 'minimum_certified':
            last = result['minimum_window']
            if result['evaluated_windows'] != list(range(first, last + 1)):
                raise ValueError('Gap in exhaustive minimum certificate')
            for n in result['evaluated_windows']:
                time = rows[result['case'], result['label'], n]['makespan_slots']
                if (time <= target) != (n == last):
                    raise ValueError('Minimum/witness contradicted by raw replay')
            if result['achieved_makespan_slots'] != rows[result['case'], result['label'], last]['makespan_slots']:
                raise ValueError('Witness time mismatch')
        elif result['status'] == 'unattained_within_registered_window_range':
            if result['evaluated_windows'] != list(range(first, 513)) or any(
                    rows[result['case'], result['label'], n]['makespan_slots'] <= target
                    for n in result['evaluated_windows']):
                raise ValueError('Invalid registered-range failure')
        else:
            raise ValueError('Unknown search status')
    for chosen in summary['selected']:
        minima = {s['case']: s['minimum_window'] for s in summary['searches']
                  if s['label'] == chosen['label'] and s['target_is_512_reference']}
        if minima != chosen['individually_minimum']:
            raise ValueError('Common selection does not use certified individual minima')
        tested = chosen['tested_common']
        if [r['window'] for r in tested] != list(range(max(minima.values()), chosen['window'] + 1)):
            raise ValueError('Gap in common-window certificate')
        for item in tested:
            actual = {c: rows[c, chosen['label'], item['window']]['makespan_slots'] for c in chosen['targets']}
            success = all(actual[c] <= t for c, t in chosen['targets'].items())
            if actual != item['times'] or success != (item['window'] == chosen['window']):
                raise ValueError('Common-window witness mismatch')
    for item in summary['ablations']:
        a = rows[item['case'], item['duplicated'], item['window']]
        b = rows[item['case'], item['configurable'], item['window']]
        if not item['equal'] or any(a[k] != b[k] for k in item['fields']):
            raise ValueError('Implementation ablation mismatch')
    for item in summary['selected_cases']:
        row = rows[item['case'], item['label'], item['window']]
        for key in ('makespan_slots', 'cost', 'request_cost', 'completion'):
            if item[key] != row[key]:
                raise ValueError('Selected-case mismatch: ' + key)
    result = dict(verified=True, raw_replays=len(rows), model_words=delivered,
                  search_certificates=len(summary['searches']), common_minima=len(summary['selected']),
                  equal_implementation_ablations=len(summary['ablations']),
                  raw_archive_sha256=summary['artifacts'][0]['sha256'],
                  scope='Independent archived counters, hashes, bound exclusions and every minimum witness; '
                        'no new replay or physical-cost calibration')
    (folder / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def render_archive(folder):
    """Standalone scientific figure of executed points only; no gap interpolation."""
    import json
    from pathlib import Path
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    folder = Path(folder)
    summary = json.loads((folder / 'summary.json').read_text())
    fig, ax = plt.subplots(figsize=(8, 4.8), layout='constrained')
    for label, name in (('home', 'Home'), ('k2', 'k2'), ('wide', 'Wide k3'),
                        ('a_dup', 'A (dup = cfg)'), ('b_dup', 'B (dup = cfg)')):
        points = sorted((r['window'], r['makespan_slots']) for r in summary['replays']
                        if r['case'] == 'dispersed9' and r['label'] == label and r['window'] <= 240)
        ax.scatter([p[0] for p in points], [p[1] for p in points], s=15, label=name)
    for target in (88, 77, 60):
        ax.axhline(target, color='.65', lw=.7, ls='--')
    ax.set(xlabel='Outstanding request entries / compute', ylabel='Task DAG completion (native slots)',
           title='Frozen dispersed9: executed integer windows', xlim=(85, 240))
    ax.legend(fontsize=9)
    ax.grid(alpha=.15)
    fig.savefig(folder / 'request_windows.svg')
    plt.close(fig)


if __name__ == '__main__':
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder')
    parser.add_argument('--render', action='store_true')
    args = parser.parse_args()
    print(json.dumps(audit_archive(args.folder), indent=2))
    if args.render:
        render_archive(args.folder)
