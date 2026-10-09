"""Fixed B1 Pair versus four-way residency; prepare all inputs before any run."""
import argparse
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import platform
import subprocess
import time

from w2w.common.fingerprints import digest_system_v2 as digest
from w2w.common.io import write_json as write
from w2w.analysis.system_summary import summarize
from w2w.provenance import revision
from w2w.workloads.semantics import logical_work
from w2w.memory.backend import RamulatorAbsolute
from w2w.network.booksim_backend import factory
from w2w.system.kernel import execute_system
from w2w.validation.system_execution import audit_system_result
from w2w.machine.presets import machine
from w2w.workloads.moe_task_graph import compile_routed_layer
from w2w.workloads.routing_input import LAYER_COHORTS, load_layer_routing


def prepare(output, policies=('pair', 'four_way')):
    output.mkdir(parents=True, exist_ok=False)
    (output/'inputs').mkdir()
    cases, layouts = [], {}
    for cohort in LAYER_COHORTS:
        work_hash = None
        for policy in policies:
            graph, metadata = compile_routed_layer(load_layer_routing(cohort=cohort), residency=policy)
            logical = digest(logical_work(graph))
            if work_hash is not None and logical != work_hash:
                raise ValueError('Residency changed logical task work')
            work_hash = logical
            layout = metadata['layout_sha256']
            if policy in layouts and layout != layouts[policy]:
                raise ValueError('Residency depends on evaluated cohort')
            layouts[policy] = layout
            name = cohort+'-'+policy
            record = dict(graph=asdict(graph), metadata=metadata)
            write(output/'inputs'/(name+'.json'), record)
            cases.append(dict(name=name, cohort=cohort, policy=policy,
                              input_sha256=digest(record), graph_sha256=digest(asdict(graph)),
                              logical_work_sha256=logical, layout_sha256=layout,
                              tokens=[t['id'] for t in metadata['tokens']],
                              weight_bytes=metadata['weight_read_bytes']))
    write(output/'registration.json', dict(schema='w2w.residency-study.v1',
        scope='one_routed_ffn_layer_timing', source_commit=revision(),
        host=platform.node(), python=platform.python_version(), cases=cases,
        spec=asdict(machine()), native='existing RamulatorAbsolute HBM2',
        network='existing native BookSim; real return only',
        primary='c0_b1', predeclared_validation=['c1_b1', 'c2_b4'],
        policy='all 128 experts; home / horizontal pair / aligned 2x2; fixed owner geometry, no trace fitting',
        max_ps=20_000_000_000))
    print(json.dumps(dict(prepared=str(output), cases=len(cases), layouts=layouts)), flush=True)


def run_case(output, name, source, binary):
    registration = json.loads((output/'registration.json').read_text())
    if revision() != registration['source_commit']:
        raise ValueError('Run source differs from frozen registration')
    case = next(c for c in registration['cases'] if c['name'] == name)
    graph, metadata = compile_routed_layer(load_layer_routing(cohort=case['cohort']), residency=case['policy'])
    record = json.loads((output/'inputs'/(name+'.json')).read_text())
    if (digest(record) != case['input_sha256']
            or digest(dict(graph=asdict(graph), metadata=metadata)) != case['input_sha256']
            or digest(asdict(machine())) != digest(registration['spec'])):
        raise ValueError('Registered input/machine changed')
    directory = output/'cases'/name
    directory.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    print(json.dumps(dict(starting=name, weight_bytes=case['weight_bytes'],
                          source=registration['source_commit'])), flush=True)
    native = RamulatorAbsolute(machine())
    try:
        result = execute_system(machine(), graph, native=native,
            network_factory=factory(source=source, binary=binary, directory=directory/'network'),
            max_ps=registration['max_ps'])
    finally:
        native.close()
    result['scope'] = 'one_routed_ffn_layer_timing'
    result['audit'] = audit_system_result(result)
    with gzip.open(directory/'result.json.gz', 'wt', compresslevel=5) as handle:
        json.dump(result, handle)
    summary = summarize(result)
    summary['wall_seconds'] = time.monotonic()-start
    write(directory/'summary.json', summary)
    write(directory/'completion.json', dict(complete=True, name=name,
        makespan_ps=result['makespan_ps'], source_commit=registration['source_commit'],
        input_sha256=case['input_sha256'], audit=result['audit']))
    print(json.dumps(dict(completed=name, makespan_us=result['makespan_ps']/1e6,
                          wall_seconds=summary['wall_seconds'], audit=result['audit'])), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--case', choices=[c+'-'+p for c in LAYER_COHORTS for p in ('home', 'pair', 'four_way')])
    parser.add_argument('--policies', nargs='+', choices=('home', 'pair', 'four_way'),
                        default=('pair', 'four_way'), help='Policies to register with --prepare')
    parser.add_argument('--booksim-source', type=Path)
    parser.add_argument('--booksim-binary', type=Path)
    args = parser.parse_args()
    if args.prepare:
        prepare(args.output, args.policies)
    else:
        if args.booksim_binary is None:
            parser.error('Running a case requires --booksim-binary; bundled runtime is the default')
        run_case(args.output, args.case, args.booksim_source, args.booksim_binary)


if __name__ == '__main__':
    main()
