"""Read completed layer records; compare timing without re-executing a simulator."""
import argparse
from collections import Counter, defaultdict
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess


from w2w.common.fingerprints import digest_system_v2 as digest


def file_record(path):
    return dict(bytes=path.stat().st_size, sha256=sha256(path.read_bytes()).hexdigest())


def distribution(values):
    values = sorted(values)
    return dict(count=len(values), mean_ps=sum(values)/len(values),
                p50_ps=values[(len(values)-1)//2],
                p95_ps=values[(len(values)-1)*95//100], max_ps=values[-1])


def inspect(result, summary):
    if result['scope'] != 'one_routed_ffn_layer_timing' or not result['audit']['passed']:
        raise ValueError('Expected a completed, audited routed FFN layer')
    if result['makespan_ps'] != summary['makespan_ps'] or not result['network']['drained']:
        raise ValueError('Summary or drain mismatch')
    requests, times = {}, defaultdict(dict)
    memory_bytes, memory_order = Counter(), defaultdict(list)
    for event in result['events']:
        kind = event['kind']
        if kind == 'read_issue':
            signature = [event[k] for k in ('task', 'memory', 'bank', 'word_address', 'bytes')]
            requests[event['request']] = signature
            memory_bytes[event['memory']] += event['bytes']
        if kind in ('read_issue', 'mc_accept', 'native_accept', 'native_ready', 'read_deliver'):
            times[event['request']][kind] = event['time_ps']
        if kind == 'native_accept':
            sig = requests[event['request']]
            memory_order[sig[1]].append(sig)
    if sum(memory_bytes.values()) != sum(t['read_bytes'] for t in result['tasks'].values()):
        raise ValueError('Issued and delivered logical weight bytes differ')
    native = result['native']
    if 'accepted_words' in native and (native['accepted_words'] != native['completed_words']
            or native['completed_words']*32 != sum(memory_bytes.values())):
        raise ValueError('Native and descriptor byte counts differ')
    if 'accepted_atoms' in native and (native['accepted_atoms'] != native['completed_atoms']
            or native['completed_atoms']*native['atomic_bytes'] != sum(memory_bytes.values())):
        raise ValueError('Native atoms and descriptor byte counts differ')
    links = {l['id']: l for l in result['spec']['links']}
    busy = sorted((dict(link=key, flits=count, utilization=count*links[key]['period_ps']/result['makespan_ps'])
                   for key, count in result['network']['link_flits'].items()
                   if links[key]['kind'] != 'HB'), key=lambda x: x['utilization'], reverse=True)
    expert_tail = max((k for k in result['tasks'] if k.startswith('expert')),
                      key=lambda k: result['tasks'][k]['finish_ps'])
    tail = summary['task_timelines'][expert_tail]
    controllers = native.get('stats', {}).get('controller', [])
    columns = ('num_read_reqs', 'num_read_reqs_served', 'avg_read_latency',
               'read_row_hits', 'read_row_misses', 'read_row_conflicts')
    channel_stats = {c['id']: {k: c[k] for k in columns}
                     for c in controllers if c['num_read_reqs']}
    return dict(
        makespan_us=result['makespan_ps']/1e6,
        graph_sha256=digest(result['graph']),
        logical_read_set_sha256=digest(sorted(requests.values())),
        native_descriptor_order_sha256={k: digest(v) for k, v in memory_order.items()},
        memory_read_bytes=dict(sorted(memory_bytes.items())),
        read_descriptors=len(requests), weight_bytes=sum(memory_bytes.values()),
        tasks=len(result['tasks']), audit=result['audit'],
        busiest_compute_links=busy[:5],
        # The native admission interval includes pending descriptor expansion and
        # controller queuing. It is not an isolated DRAM-command latency.
        descriptor_intervals={name: distribution([t[end]-t[start] for t in times.values()])
            for name, start, end in (
                ('issue_to_mc', 'read_issue', 'mc_accept'),
                ('native_admission_to_ready', 'native_accept', 'native_ready'),
                ('native_ready_to_delivery', 'native_ready', 'read_deliver'))},
        last_expert_task=dict(id=expert_tail, **tail,
            allocation_to_last_native_ready_ps=(tail['last_native_ready_ps']-tail['allocated_ps']
                if tail['last_native_ready_ps'] is not None else None),
            last_read_after_last_native_ready_ps=(tail['last_read_delivery_ps']-tail['last_native_ready_ps']
                if tail['last_native_ready_ps'] is not None else None)),
        channel_stats=channel_stats,
        row_totals={k: sum(c[k] for c in channel_stats.values())
                    for k in ('read_row_hits', 'read_row_misses', 'read_row_conflicts')},
        physical=result['physical'], native_kind=native['kind'],
        native_identity={k: native[k] for k in ('upstream_commit', 'bridge_sha256', 'config_sha256') if k in native},
        network_identity=result['network']['identity'],
        network_source_commit=result['network']['source_commit'],
        wire_bytes_by_class_including_HB=result['network']['wire_bytes_by_class'])


def analyze(directories):
    studies, manifests, hashes = {}, {}, set()
    for directory in directories:
        registration = json.loads((directory/'registration.json').read_text())
        summary = json.loads((directory/'summary.json').read_text())
        completion = json.loads((directory/'completion.json').read_text())
        if not completion['complete']:
            raise ValueError('Incomplete experiment')
        study = {}
        manifests[str(directory)] = {n: file_record(directory/n)
                                    for n in ('input.json', 'registration.json', 'summary.json', 'completion.json')}
        for case in registration['cases']:
            name = case['name']
            path = directory/(name+'.json.gz')
            with gzip.open(path, 'rt') as handle:
                result = json.load(handle)
            if result['spec'] != case['spec'] or result['makespan_ps'] != completion['cases'][name]:
                raise ValueError('Execution differs from registration/completion')
            row = inspect(result, summary[name])
            if row['graph_sha256'] != registration['graph_sha256']:
                raise ValueError('Task graph differs from registration')
            hashes.add((row['graph_sha256'], row['logical_read_set_sha256']))
            study[name] = row
            manifests[str(directory)][path.name] = file_record(path)
        base = study['B1-real']['makespan_us']
        for row in study.values():
            row['completion_time_change_percent'] = 100*(row['makespan_us']/base-1)
        profile = registration['dram_backend']
        if profile in studies:
            raise ValueError('Duplicate DRAM profile')
        studies[profile] = dict(source_commit=registration['source_commit'],
                               host=registration['host'], cases=study)
    if len(hashes) != 1:
        raise ValueError('Logical graph/addresses changed across conditions')
    return dict(schema='w2w.moe-layer-analysis.v1', scope='one_routed_ffn_layer_timing',
                analysis_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                identical_graph_and_logical_reads=True, studies=studies, files=manifests)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({profile: {k: v['makespan_us'] for k, v in rows['cases'].items()}
                      for profile, rows in result['studies'].items()}))


if __name__ == '__main__':
    main()
