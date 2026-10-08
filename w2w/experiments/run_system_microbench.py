"""Registered causal microbenchmarks; no routing trace or application-speedup claim."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import platform
import subprocess

from w2w.domain.execution import ComputeTask, ControlEdge, DataEdge, ExecutionGraph, ReadAccess, ResidentObject
from w2w.domain.system import mesh_system
from w2w.system.kernel import execute_system
from w2w.validation.system_execution import audit_system_result


def closed_loop_fixture():
    spec = mesh_system()
    graph = ExecutionGraph(
        (ComputeTask('producer', 'c0', 5),
         ComputeTask('expert', 'c1', 8, (ReadAccess('weight', 0, 256),)),
         ComputeTask('consumer', 'c0', 3)),
        (ResidentObject('weight', 'm0', 0, 256),),
        (DataEdge('dispatch', 'producer', 'expert', 128),
         DataEdge('combine', 'expert', 'consumer', 64)))
    return spec, graph


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--native', action='store_true', help='Use the existing pinned HBM2 bridge')
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Use a fresh output path')
    spec, graph = closed_loop_fixture()
    cases = [('B1', spec, graph),
             ('long_links', replace(spec, links=tuple(replace(l, pipeline_cycles=l.pipeline_cycles+4,
                                                           credit_cycles=l.credit_cycles+4) for l in spec.links)), graph),
             ('small_window', replace(spec, outstanding_per_tile=1), graph),
             ('B0_local_weights', replace(spec, baseline='B0'), replace(graph, objects=(ResidentObject('weight', 'm1', 0, 256),))),
             ('control_only', spec, ExecutionGraph((ComputeTask('a', 'c0', 5), ComputeTask('b', 'c1', 1)),
                                                  control=(ControlEdge('a', 'b'),)))]
    results = []
    for name, design, workload in cases:
        native = None
        if args.native:
            from w2w.memory.backend import RamulatorAbsolute
            native = RamulatorAbsolute(design)
        try:
            result = execute_system(design, workload, native=native)
            result['audit'] = audit_system_result(result)
            result['name'] = name
            results.append(result)
        finally:
            if native is not None: native.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    record = dict(schema='w2w.system-microbench.v2', scope='system_execution_v2_prototype',
                  source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  git_status=subprocess.check_output(['git', 'status', '--porcelain'], text=True),
                  host=platform.node(), python=platform.python_version(), results=results)
    args.output.write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps([dict(name=r['name'], makespan_ps=r['makespan_ps'], audit=r['audit']) for r in results], indent=2))


if __name__ == '__main__':
    main()
