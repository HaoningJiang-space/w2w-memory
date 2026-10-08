"""One real-routing MoE layer, fixed graph/residency, three transport conditions."""
import argparse
from dataclasses import asdict
import gzip
from hashlib import sha256
import json
from pathlib import Path
import platform
import subprocess
import time

from w2w.network.booksim_backend import factory
from w2w.system.kernel import execute_system
from w2w.validation.system_execution import audit_system_result
from w2w.workloads.moe_task_graph import compile_layer, machine


def write(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def summarize(result):
    events = result['events']
    read_ready, reads, allocations, inputs = {}, {}, {}, {}
    for e in events:
        if e['kind'] == 'read_issue': reads[e['request']] = e['task']
        elif e['kind'] == 'native_ready': read_ready[reads[e['request']]] = e['time_ps']
        elif e['kind'] == 'task_allocate': allocations[e['task']] = e['time_ps']
        elif e['kind'] == 'data_deliver':
            edge = next(x for x in result['graph']['data'] if x['id'] == e['edge'])
            inputs[edge['consumer']] = e['time_ps']
    delivered = {}
    for e in events:
        if e['kind'] == 'read_deliver': delivered[e['task']] = e['time_ps']
    links = {l['id']: l for l in result['spec']['links']}
    busiest = sorted((dict(link=k, kind=links[k]['kind'], flits=v,
                           busy_ps=v*links[k]['period_ps'],
                           utilization=v*links[k]['period_ps']/result['makespan_ps'])
                       for k,v in result['network']['link_flits'].items()),
                      key=lambda r:r['busy_ps'], reverse=True)[:10]
    timelines = {key: dict(allocated_ps=allocations[key], last_native_ready_ps=read_ready.get(key),
                           last_read_delivery_ps=delivered.get(key), last_input_delivery_ps=inputs.get(key), **row)
                 for key,row in result['tasks'].items()}
    return dict(makespan_ps=result['makespan_ps'], drained_ps=result['drained_ps'],
                native=result['native'], network=result['network'], physical=result['physical'],
                compute_busy_ps=result['compute_busy_ps'], sram_peak_bytes=result['sram_peak_bytes'],
                outstanding_peak=result['outstanding_peak'], mc_peak=result['mc_peak'],
                busiest_links=busiest, task_timelines=timelines, audit=result['audit'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--booksim-source', type=Path, required=True)
    p.add_argument('--booksim-binary', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    graph, metadata = compile_layer()
    graph_sha = sha256(json.dumps(asdict(graph), sort_keys=True).encode()).hexdigest()
    write(args.output/'input.json', dict(metadata=metadata, graph_sha256=graph_sha, graph=asdict(graph)))
    cases = [('B1-real', False, False), ('B1-return-ideal', False, True), ('B1-wide-NoC', True, False)]
    registration = dict(schema='w2w.moe-layer-study.v1', source_commit=subprocess.check_output(
        ['git','rev-parse','HEAD'],text=True).strip(), host=platform.node(),
        graph_sha256=graph_sha, python=platform.python_version(),
        cases=[dict(name=name, ideal_return=ideal, spec=asdict(machine(wide=wide))) for name,wide,ideal in cases])
    write(args.output/'registration.json', registration)
    summaries = {}
    for name, wide, ideal in cases:
        start = time.monotonic()
        print(json.dumps(dict(starting=name, weight_bytes=metadata['weight_read_bytes'],
                              graph_sha256=graph_sha)), flush=True)
        result = execute_system(machine(wide=wide), graph,
            network_factory=factory(source=args.booksim_source, binary=args.booksim_binary,
                                    directory=args.output/name, ideal_return=ideal),
            max_ps=2_000_000_000)
        result['audit'] = audit_system_result(result)
        result['scope'] = 'one_routed_ffn_layer_timing'
        with gzip.open(args.output/(name+'.json.gz'), 'wt', compresslevel=5) as f:
            json.dump(result, f)
        summaries[name] = summarize(result)
        summaries[name]['wall_seconds'] = time.monotonic()-start
        write(args.output/'summary.json', summaries)
        print(json.dumps(dict(completed=name, makespan_ps=result['makespan_ps'],
                              wall_seconds=summaries[name]['wall_seconds'], audit=result['audit'])), flush=True)
    write(args.output/'completion.json', dict(complete=True, graph_sha256=graph_sha,
                                            cases={k:v['makespan_ps'] for k,v in summaries.items()}))


if __name__ == '__main__': main()
