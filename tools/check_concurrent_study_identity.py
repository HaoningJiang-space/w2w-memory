#!/usr/bin/env python3
"""Cross-check frozen S0/S1 work, layout and physical budgets after raw audits."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def check(root):
    registrations = {}
    inputs = {}
    audits = {}
    for execution in ('s0', 's1'):
        registrations[execution] = reg = json.loads((root / execution / 'registration.json').read_text())
        audits[execution] = audit = json.loads((root / f'{execution}-analysis.json').read_text())
        if not audit['passed'] or audit['execution_source_commit'] != reg['source_commit']:
            raise ValueError('Completed independent audit/source identity required')
        inputs[execution] = {}
        for policy, case in reg['cases'].items():
            with gzip.open(root / execution / 'inputs' / f'{policy}.json.gz', 'rt') as f:
                data = json.load(f)
            if digest(data) != case['input_sha256'] or digest(data['weights']) != case['weight_layout_sha256']:
                raise ValueError('Frozen input or weight identity changed')
            inputs[execution][policy] = data
    if registrations['s0']['source_commit'] != registrations['s1']['source_commit']:
        raise ValueError('Cross-schedule study must use one execution source')
    base = inputs['s0']['reference']
    fields = ('machine', 'resources', 'compute_reference_weights', 'cache', 'network_policy',
              'compute_contexts', 'operand_readiness', 'refresh', 'request_control')
    s0_edges = {(e['producer'], e['consumer']) for e in base['graph']['control']}
    removed = {(a, b) for a, b in s0_edges if a.endswith('/gate') and b == a[:-4] + 'up'}
    added = {(a, b[:-4] + 'up') for a, b in s0_edges
             if a.endswith('/accumulate') and b.endswith('/gate')}
    if not removed or not added:
        raise ValueError('Expected frozen projection and previous-block barriers')
    work = ('logical_sha256', 'macs', 'vector_ops', 'weight_read_bytes', 'compute_placement_sha256')
    for execution, cases in inputs.items():
        for policy, data in cases.items():
            if any(data[name] != base[name] for name in fields):
                raise ValueError('Cross-schedule physical/compute/cache budget changed')
            if any(data['graph'][name] != base['graph'][name] for name in ('tasks', 'data')):
                raise ValueError('Mathematical tasks or tensor edges changed')
            if any(data['metadata'][name] != base['metadata'][name] for name in work):
                raise ValueError('Logical/arithmetic/compute placement identity changed')
            edges = {(e['producer'], e['consumer']) for e in data['graph']['control']}
            if len(edges) != len(data['graph']['control']) or edges != (s0_edges if execution == 's0' else s0_edges - removed | added):
                raise ValueError('Unexpected control dependency or next-block prefetch')
            fetch = data.get('fetch_policy')
            if fetch != (None if execution == 's0' else dict(contexts_per_cluster=2,
                    read_issue_policy='round_robin', metadata_bytes_per_cluster=136)):
                raise ValueError('Unexpected finite fetch policy')
    paired = sorted(set(inputs['s0']) & set(inputs['s1']))
    for policy in paired:
        if inputs['s0'][policy]['weights'] != inputs['s1'][policy]['weights'] or inputs['s0'][policy]['graph']['objects'] != inputs['s1'][policy]['graph']['objects']:
            raise ValueError('A schedule comparison changed physical weight addresses')
    for execution in inputs:
        reference = {w['tensor']: w for w in inputs[execution]['reference']['weights']}
        for w in inputs[execution]['phase-split']['weights']:
            if w['tensor'].endswith(('/gate', '/down')) and w != reference[w['tensor']]:
                raise ValueError('Phase-Split changed locked Gate/Down physical identity')
    rows = [row for audit in audits.values() for row in audit['cases'].values()]
    if any(not row['independent_passed'] for row in rows) or len({(r['booksim_sha256'], r['bridge_sha256']) for r in rows}) != 1:
        raise ValueError('Native tools or independent audit changed')
    if len({(r['audit']['native_bytes'], r['audit']['tasks'], r['audit']['physical_domains']) for r in rows}) != 1:
        raise ValueError('Executed work/native resource count changed')
    migration = json.loads((root / 's0-reference-migration.json').read_text())
    if not migration['passed'] or not migration['physical_record_equal']:
        raise ValueError('S0 complete physical-record migration failed')
    return dict(schema='w2w.concurrent-study-identity.v1', passed=True,
        execution_source_commit=registrations['s0']['source_commit'],
        checker_source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        work_sha256=digest({name: base['metadata'][name] for name in work}),
        physical_budget_sha256=digest({name: base[name] for name in fields}),
        paired_layouts=paired, removed_gate_up_barriers=len(removed),
        added_previous_block_up_barriers=len(added),
        tasks=len(base['graph']['tasks']), catalog_matrices=len(base['weights']),
        native_bytes=rows[0]['audit']['native_bytes'], physical_domains=rows[0]['audit']['physical_domains'],
        s0_physical_record_migration=migration,
        contract='Only projection dependency and paid bounded fetch/round-robin policy differ across S0/S1; '
                 'identical mathematical work, compute placement, paired physical addresses and data resources. '
                 'This is not an isolated graph-edge-only intervention or a silicon/PPA validation.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = check(a.root)
    a.output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
