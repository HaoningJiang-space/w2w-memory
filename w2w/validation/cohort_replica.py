"""Compare independently audited frozen replays across execution hosts.

Execution fields are exact; only floating cost proxies allow rounding error.
This is a determinism check of one registered study, not new workload evidence.
"""
import argparse
from hashlib import sha256
import json
from math import isclose, isfinite
from pathlib import Path

from w2w.validation.cohort_replay import audit
from w2w.workloads.cohort_replay import read_json


def compare_rows(primary, replica):
    if primary.keys() != replica.keys():
        raise ValueError('Replay field coverage differs')
    for key in primary.keys() - {'wall_seconds', 'cost'}:
        if primary[key] != replica[key]:
            raise ValueError(f'Execution field differs: {key}')
    a, b = primary['cost'], replica['cost']
    if a.keys() != b.keys():
        raise ValueError('Cost field coverage differs')
    rounding = {}
    for key in a:
        x, y = a[key], b[key]
        if type(x) is float and type(y) is float:
            if not (isfinite(x) and isfinite(y) and isclose(x, y, rel_tol=1e-12, abs_tol=1e-12)):
                raise ValueError(f'Cost differs: {key}')
            if x != y:
                rounding[key] = abs(x-y)
        elif x != y:
            raise ValueError(f'Cost differs: {key}')
    return rounding


def compare(primary, replica, inputs):
    primary, replica = Path(primary), Path(replica)
    audits = [audit(path, inputs) for path in (primary, replica)]
    summaries = [read_json(path/'summary.json') for path in (primary, replica)]
    if summaries[0]['provenance']['host'] == summaries[1]['provenance']['host']:
        raise ValueError('Cross-host comparison requires different recorded hosts')
    identities = lambda s: {(r['case'], r['label'], r['mode']): r for r in s['results']}
    a, b = map(identities, summaries)
    if a.keys() != b.keys():
        raise ValueError('Different registered jobs')
    rounding = {}
    for key in sorted(a):
        diffs = compare_rows(read_json(primary/a[key]['path']), read_json(replica/b[key]['path']))
        for field, delta in diffs.items():
            rounding[field] = max(rounding.get(field, 0.), delta)
    return dict(schema='w2w.cohort-cross-host.v1', verified=True, records=len(a),
                delivered_words_per_run=audits[0]['delivered_words'],
                executions=[s['provenance'] for s in summaries],
                summary_sha256=[sha256((p/'summary.json').read_bytes()).hexdigest() for p in (primary,replica)],
                exact_execution_fields=True, cost_rounding_max_abs=rounding,
                ignored_field='wall_seconds',
                scope='Same 81 registered cases repeated on two hosts; not 162 independent workload samples')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('primary', 'replica', 'inputs', 'output'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    result = compare(args.primary, args.replica, args.inputs)
    Path(args.output).write_text(json.dumps(result, indent=2)+'\n')
    print('VERIFIED', result['records'], 'cross-host replay pairs')


if __name__ == '__main__':
    main()
