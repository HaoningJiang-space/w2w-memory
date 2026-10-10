#!/usr/bin/env python3
"""Retain observational gateway bins from independently hashed cold executions."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    cases = {}
    for execution in ('s0', 's1'):
        audit = json.loads((a.root / f'{execution}-analysis.json').read_text())
        if not audit['passed']:
            raise ValueError('Independent audit required')
        for policy, row in audit['cases'].items():
            path = a.root / execution / 'cases' / policy / 'result.json.gz'
            raw_sha = sha(path)
            if raw_sha != audit['files'][f'cases/{policy}/result.json.gz']['sha256']:
                raise ValueError('Audited raw result changed')
            with gzip.open(path, 'rt') as f:
                result = json.load(f)
            if result['makespan_ps'] != row['makespan_ps'] or result['source_commit'] != audit['execution_source_commit']:
                raise ValueError('Execution identity changed')
            cases[f'{execution}-{policy}'] = dict(raw_result_sha256=raw_sha,
                makespan_ps=result['makespan_ps'], execution_source_commit=result['source_commit'],
                network_event_level=result['network']['event_level'],
                gateway_bytes=result['native']['gateway_bytes'],
                gateway_busy_cycles=result['native']['gateway_busy_cycles'],
                gateway_service_bins=result['native'].get('gateway_service_bins'))
            del result
    output = dict(schema='w2w.audited-gateway-series.v1', passed=True, cases=cases,
        contract='Actual payload/busy bins, not a performance model or continuous-busy proof. '
                 'Transaction captures contain admission/delivery and aggregate executed hops, not individual flit-hop timestamps.')
    a.output.write_text(json.dumps(output, sort_keys=True, indent=2) + '\n')
    print(json.dumps(dict(passed=True, cases={k:dict(makespan_ps=v['makespan_ps'],
        event_level=v['network_event_level'], recorded_bins=v['gateway_service_bins'] is not None) for k,v in cases.items()})))


if __name__ == '__main__':
    main()
