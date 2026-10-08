"""Inspect direct memory connectivity and reproduce excluded communication costs.

This is a model-boundary audit, not a network implementation or a new workload
benchmark. It intentionally leaves all execution and geometry semantics intact.
"""
import argparse
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import networkx as nx

from tests.fixtures.tiny_fabric import two_compute_two_memory
from w2w.domain import EndpointSpec, StaticLayout
from w2w.provenance import provenance
from w2w.service.cost import CostModel
from w2w.service.guaranteed_service_exchange import contoured_geometry
from w2w.service.read_replay import ReadReplayConfig, replay_reads
from w2w.workloads.read_trace import ReadObject, ReadSpan, ReadTask, ReadTrace


def audit():
    physical = contoured_geometry()
    graph = nx.Graph()
    graph.add_nodes_from(('C', c) for c in range(len(physical.compute)))
    graph.add_nodes_from(('M', m) for m in range(len(physical.memory)))
    graph.add_edges_from((('C', e['c']), ('M', e['m'])) for e in physical.edges)
    direct = {(e['c'], e['m']) for e in physical.edges}
    assert all(a[0] != b[0] for a, b in graph.edges)
    shared = next((c, d, m) for c, m in sorted(direct)
                  for d, n in sorted(direct) if n == m and d != c)
    c, d, m = shared
    assert nx.shortest_path_length(graph, ('C', c), ('C', d)) == 2
    result = dict(schema='w2w.simulator-connectivity-audit.v1', provenance=provenance(),
        topology=dict(computes=len(physical.compute), memories=len(physical.memory),
            physical_cm_port_edges=len(physical.edges), distinct_cm_pairs=len(direct),
            cc_edges=0, mm_edges=0, structural_components=nx.number_connected_components(graph),
            geometric_two_hop_example=[['C', c], ['M', m], ['C', d]],
            forwarding_supported=physical.summary()['forwarding_supported']))

    # A geometric path through another compute does not create a legal read.
    tiny = two_compute_two_memory()
    clipped = replace(tiny, geometry=replace(tiny.geometry, routes=tiny.geometry.routes[:-1]))
    path_graph = nx.Graph()
    path_graph.add_edges_from((('C', c), ('M', m)) for c, m, *_ in clipped.geometry.routes)
    path = nx.shortest_path(path_graph, ('C', 0), ('M', 1))
    assert len(path) == 4
    read = ReadTrace((ReadObject('a', 128, 0),),
        (ReadTask('read', 0, (ReadSpan('a', 0, 128),)),), 'synthetic', 'direct-only adversary')
    try:
        replay_reads(clipped, read)
    except (ValueError, KeyError) as error:
        result['non_direct_read'] = dict(geometric_path=path, rejected=True,
                                         error_type=type(error).__name__, error=str(error))
    else:
        raise AssertionError('Indirect-only memory unexpectedly became reachable')

    home = replace(tiny, structure='home', home_fraction=1,
        exposure=replace(tiny.exposure, mask=((0,),), port_bits=(8000, 0, 0)),
        endpoint=EndpointSpec((256, 0, 0), (0, 0, 0), mode='direct'),
        layout=StaticLayout(((1., 0.), (0., 1.))))
    cfg = ReadReplayConfig(request_latency_slots=0, native_latency_slots=0, link_latency_slots=0)
    control = ReadTrace((), (ReadTask('producer', 0, compute_slots=7),
        ReadTask('consumer', 1, dependencies=('producer',), compute_slots=3)),
        'synthetic', 'Control precedence is not modeled data communication')
    dependence = replay_reads(home, control, replace(cfg, link_latency_slots=100))
    consumer = next(t for t in dependence['tasks'] if t['id'] == 'consumer')
    assert consumer['start_slot'] == 7 and dependence['makespan_slots'] == 10
    assert dependence['audit']['sent_bits'] == 0
    result['cross_compute_precedence'] = dict(start=consumer['start_slot'], finish=dependence['makespan_slots'],
        configured_memory_link_latency=100, sent_bits=0,
        meaning='Control-only precedence accepted; no C-to-C packet or synchronization transport modeled')

    # Changing the wire-pipeline cost proxy does not change replay latency.
    sparse = replace(home, geometry=replace(home.geometry, bank_xy=((5., 0.),)))
    dense = replace(sparse, exposure=replace(sparse.exposure, pipeline_spacing_mm=.5))
    rows = [replay_reads(design, read, cfg) for design in (sparse, dense)]
    costs = [CostModel.evaluate(design)['pipeline_register_bits'] for design in (sparse, dense)]
    assert costs[0] != costs[1] and rows[0]['makespan_slots'] == rows[1]['makespan_slots']
    result['pipeline_cost_vs_latency'] = dict(spacings_mm=[2., .5], pipeline_bits=costs,
        makespan_slots=[r['makespan_slots'] for r in rows],
        meaning='Physical pipeline spacing is a cost proxy, not an input to replay link latency')

    base = Path('artifacts/results/workload/cohort_replay')
    input_summary = json.loads((base/'inputs/summary.json').read_text())
    traces = [base/'inputs'/r['path'] for r in input_summary['files'] if r['path'].endswith('_trace.json')]
    compiled = [ReadTrace.from_record(json.loads(p.read_text())) for p in traces]
    summary = json.loads((base/'flow/summary.json').read_text())
    assert len(compiled) == 45 and len(summary['results']) == 81
    assert all(t.compute_slots == 0 for trace in compiled for t in trace.tasks)
    result['published_cohort'] = dict(source_commit=summary['provenance']['commit'],
        replay_records=81, logical_traces=45,
        tasks_with_compute_time=sum(t.compute_slots > 0 for tr in compiled for t in tr.tasks),
        dependency_transport_fields=[],
        summary_sha256=sha256((base/'flow/summary.json').read_bytes()).hexdigest(),
        scope='Captured expert choices compile to full weight reads and zero-time joins; no dispatch/combine/GEMM')
    result['verified'] = True
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    record = audit()
    Path(args.output).write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(record, indent=2))
