"""Compare registered static layouts using completed full-system records only."""
import argparse
from collections import defaultdict
import gzip
import json
from pathlib import Path
import subprocess

from w2w.analysis.moe_layer import digest, distribution, file_record, inspect


def task_work(graph):
    return dict(tasks=[dict(**{k: v for k, v in t.items() if k != 'reads'},
                            weight_bytes=sum(r['size_bytes'] for r in t['reads']))
                       for t in graph['tasks']], data=graph['data'], control=graph['control'])


def mc_waits(result):
    memory, times = {}, defaultdict(dict)
    for event in result['events']:
        kind = event['kind']
        if kind == 'read_issue':
            memory[event['request']] = event['memory']
        if kind in ('read_issue', 'mc_accept', 'native_accept', 'native_ready', 'read_deliver'):
            times[event['request']][kind] = event['time_ps']
    grouped = defaultdict(lambda: defaultdict(list))
    for key, t in times.items():
        for name, start, end in (
            ('issue_to_mc', 'read_issue', 'mc_accept'),
            ('native_admission_to_ready', 'native_accept', 'native_ready'),
            ('ready_to_delivery', 'native_ready', 'read_deliver')):
            grouped[memory[key]][name].append(t[end]-t[start])
    return {m: {k: distribution(v) for k, v in row.items()} for m, row in grouped.items()}


def network_parameters(directory, identity):
    """Compare execution parameters; absolute input/output filenames vary by run."""
    root = (directory/'network').resolve()
    config = root/'rapidchiplet/booksim2/src/rc_configs/network.conf'
    topology = root/'rapidchiplet/booksim2/src/rc_topologies/network.anynet'
    if file_record(config)['sha256'] != identity['config_sha256']:
        raise ValueError('Native configuration file differs from executed identity')
    text = config.read_text()
    for key, name in (('trace_file', 'empty_network_input.json'), ('trace_report', 'trace_report.json')):
        original = f'{key} = {root/name};'
        if text.count(original) != 1:
            raise ValueError('Unexpected native input/output path')
        text = text.replace(original, f'{key} = <run>/{name};')
    if json.loads((root/'empty_network_input.json').read_text()) != []:
        raise ValueError('Unexpected offline trace in live network')
    parameters = {k: v for k, v in identity.items() if k != 'config_sha256'}
    parameters.update(normalized_config_sha256=digest(text), topology_sha256=file_record(topology)['sha256'])
    return parameters, (config, topology, root/'empty_network_input.json')


def analyze(source, cohorts=None):
    registration = json.loads((source/'registration.json').read_text())
    if registration['schema'] != 'w2w.residency-study.v1':
        raise ValueError('Wrong experiment registration')
    cohorts = cohorts or ['c0_b1', 'c1_b1', 'c2_b4']
    rows, files, identities, layouts = {}, {}, set(), {}
    for case in registration['cases']:
        if case['cohort'] not in cohorts:
            continue
        name = case['name']
        directory = source/'cases'/name
        completion = json.loads((directory/'completion.json').read_text())
        summary = json.loads((directory/'summary.json').read_text())
        record = json.loads((source/'inputs'/(name+'.json')).read_text())
        with gzip.open(directory/'result.json.gz', 'rt') as handle:
            result = json.load(handle)
        if (not completion['complete'] or completion['source_commit'] != registration['source_commit']
                or result['spec'] != registration['spec'] or result['graph'] != record['graph']
                or digest(record) != case['input_sha256']
                or digest(task_work(result['graph'])) != case['logical_work_sha256']
                or completion['makespan_ps'] != result['makespan_ps']):
            raise ValueError('Result/registration/input identity mismatch')
        layout = digest(result['graph']['objects'])
        policy = case['policy']
        if layout != case['layout_sha256'] or (policy in layouts and layout != layouts[policy]):
            raise ValueError('All-expert layout changed across requests')
        layouts[policy] = layout
        row = inspect(result, summary)
        if row['native_kind'] != 'ramulator_hbm2_reference_v1' or result['network']['ideal_return']:
            raise ValueError('This study requires HBM2 and a real NoC return')
        parameters, network_files = network_parameters(directory, row['network_identity'])
        row['network_parameters'] = parameters
        identities.add(digest([row['native_identity'], parameters, row['network_source_commit']]))
        links = {l['id']: l for l in result['spec']['links']}
        row.update(logical_work_sha256=case['logical_work_sha256'], layout_sha256=layout,
            tokens=case['tokens'], token_count=len(case['tokens']),
            logical_experts=len({k.split('/')[0] for k in result['tasks'] if k.startswith('expert')}),
            active_memories=len(row['memory_read_bytes']), peak_memory_bytes=max(row['memory_read_bytes'].values()),
            noc_wire_bytes=sum(result['network']['wire_bytes_by_class'].values()),
            noc_flit_hops=sum(v for k, v in result['network']['link_flits'].items() if links[k]['kind'] != 'HB'),
            mc_waits=mc_waits(result), mc_peak=result['mc_peak'],
            outstanding_peak=result['outstanding_peak'], sram_peak_bytes=result['sram_peak_bytes'],
            wall_seconds=summary['wall_seconds'])
        rows.setdefault(case['cohort'], {})[policy] = row
        for path in (source/'inputs'/(name+'.json'), directory/'result.json.gz',
                     directory/'summary.json', directory/'completion.json', *network_files):
            files[str(path)] = file_record(path)
    if len(identities) != 1 or set(rows) != set(cohorts):
        raise ValueError('Component identity or cohort coverage differs')
    comparisons = {}
    for cohort, policies in rows.items():
        a, b = policies['pair'], policies['four_way']
        if a['logical_work_sha256'] != b['logical_work_sha256'] or a['tokens'] != b['tokens']:
            raise ValueError('Paired runs have different logical work')
        comparisons[cohort] = dict(pair_us=a['makespan_us'], four_way_us=b['makespan_us'],
            completion_reduction_percent=100*(1-b['makespan_us']/a['makespan_us']),
            noc_wire_increase_percent=100*(b['noc_wire_bytes']/a['noc_wire_bytes']-1),
            pair_active_memories=a['active_memories'], four_way_active_memories=b['active_memories'],
            pair_peak_memory_bytes=a['peak_memory_bytes'], four_way_peak_memory_bytes=b['peak_memory_bytes'])
    files[str(source/'registration.json')] = file_record(source/'registration.json')
    return dict(schema='w2w.residency-analysis.v1', scope=registration['scope'],
        source_commit=registration['source_commit'],
        analysis_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        cohorts=rows, comparisons=comparisons, frozen_layouts=layouts,
        all_registered_cases_complete=len(rows)==3, files=files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cohort', choices=('c0_b1', 'c1_b1', 'c2_b4'), action='append')
    args = parser.parse_args()
    result = analyze(args.source, args.cohort)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result['comparisons']))


if __name__ == '__main__':
    main()
