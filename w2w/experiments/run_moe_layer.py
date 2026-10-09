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
from w2w.common.io import write_json as write
from w2w.analysis.system_summary import summarize


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--booksim-source', type=Path, help='Optional legacy wafer_simulator checkout; default is bundled')
    p.add_argument('--booksim-binary', type=Path, required=True)
    p.add_argument('--dram', choices=('ideal', 'ramulator'), default='ideal')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    graph, metadata = compile_layer()
    graph_sha = sha256(json.dumps(asdict(graph), sort_keys=True).encode()).hexdigest()
    write(args.output/'input.json', dict(metadata=metadata, graph_sha256=graph_sha, graph=asdict(graph)))
    cases = [('B1-real', False, False), ('B1-return-ideal', False, True), ('B1-wide-NoC', True, False)]
    registration = dict(schema='w2w.moe-layer-study.v1', source_commit=subprocess.check_output(
        ['git','rev-parse','HEAD'],text=True).strip(), host=platform.node(),
        graph_sha256=graph_sha, python=platform.python_version(), dram_backend=args.dram,
        cases=[dict(name=name, ideal_return=ideal, spec=asdict(machine(wide=wide))) for name,wide,ideal in cases])
    write(args.output/'registration.json', registration)
    summaries = {}
    for name, wide, ideal in cases:
        start = time.monotonic()
        print(json.dumps(dict(starting=name, weight_bytes=metadata['weight_read_bytes'],
                              graph_sha256=graph_sha)), flush=True)
        spec = machine(wide=wide)
        native = None
        if args.dram == 'ramulator':
            from w2w.memory.backend import RamulatorAbsolute
            native = RamulatorAbsolute(spec)
        try:
            result = execute_system(spec, graph, native=native,
                network_factory=factory(source=args.booksim_source, binary=args.booksim_binary,
                                        directory=args.output/name, ideal_return=ideal),
                max_ps=2_000_000_000)
        finally:
            if native is not None: native.close()
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
