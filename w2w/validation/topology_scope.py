"""Witness the current direct-memory model boundary, without adding a NoC.

A connected geometric overlap graph is not an executable forwarding network.
These probes document that distinction and do not evaluate a routed alternative.
"""
import argparse
from collections import Counter
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import networkx as nx
import numpy as np

from w2w.provenance import provenance
from w2w.service.adapters import DesignFabric
from w2w.service.read_replay import ReadReplayConfig, replay_reads
from w2w.service.solver import FixedService
from w2w.synthesis.cohort_replay import designs
from w2w.workloads.read_residency import ReadResidency
from w2w.workloads.read_trace import ReadObject, ReadSpan, ReadTask, ReadTrace


def audit():
    catalog = designs()
    design = catalog['c']
    geometry = design.geometry
    graph = nx.Graph()
    graph.add_nodes_from(f'C{i}' for i in range(len(geometry.compute_xy)))
    graph.add_nodes_from(f'M{i}' for i in range(len(geometry.memory_xy)))
    for c, m, *_ in geometry.routes:
        graph.add_edge(f'C{c}', f'M{m}')
    assert nx.is_connected(graph)
    assert all(a[0] != b[0] for a, b in graph.edges)

    fabrics = {name: DesignFabric(value) for name, value in catalog.items()}
    for fabric in fabrics.values():
        for (compute, bank), edges in fabric.paths.items():
            assert all(fabric.edges[i]['c'] == compute and
                       fabric.edges[i]['m'] == bank // fabric.banks for i in edges)

    # Deliberately demand bytes on a memory reachable only by graph traversal.
    # Use the full-width reference to avoid confusing exposure with geometry.
    fabric = fabrics['wide']
    remote = max((m for m in range(fabric.nm) if not graph.has_edge('C0', f'M{m}')),
                 key=lambda m: nx.shortest_path_length(graph, 'C0', f'M{m}'))
    bank = remote * fabric.banks
    shares = np.zeros((fabric.nc, fabric.nm*fabric.banks))
    shares[0, bank] = 1.
    service = FixedService(fabric, SimpleNamespace(shares=shares))
    demand = np.zeros(fabric.nc); demand[0] = 1.
    no_floor, floor = service.solve(demand, minimum=0), service.solve(demand, minimum=1)
    assert (0, bank) not in fabric.paths
    assert no_floor['served_tb_s'][0] == 0 and not floor['feasible']

    # Actual finite return execution on a small frozen address stream.
    trace = ReadTrace((ReadObject('weights', 7168, 0),),
                      (ReadTask('read', 0, (ReadSpan('weights', 0, 7168),)),),
                      'synthetic', 'topology scope diagnostic, not performance evidence')
    residence = ReadResidency(design, trace)
    targets = Counter()
    for logical in trace.words(trace.tasks[0]):
        b, _, p, edge = residence.locate(*logical)
        physical = residence.fabric.edges[edge]
        assert physical['c'] == 0 and physical['m'] == b//fabric.banks and physical['mp'] == p
        targets[physical['m']] += 1
    result = replay_reads(design, trace)
    assert result['audit']['delivered_words'] == 224

    # Cross-compute DAG dependencies are ordering, not modeled messages.
    dag = ReadTrace((), (ReadTask('producer', 0, compute_slots=5),
                        ReadTask('consumer', fabric.nc-1, dependencies=('producer',), compute_slots=1)),
                    'synthetic', 'zero-payload dependency diagnostic')
    cfg = ReadReplayConfig()
    dependencies = [replay_reads(design, dag, replace(cfg, link_latency_slots=latency)) for latency in (1, 100)]
    assert all(row['makespan_slots'] == 6 and not row['routes'] for row in dependencies)
    paths = ['w2w/domain/design.py', 'w2w/service/read_replay.py', 'w2w/service/adapters.py',
             'w2w/service/solver.py', 'w2w/workloads/patterns_trace.py',
             'w2w/experiments/run_cohort_replay.py']
    return dict(schema='w2w.topology-scope.v1', verified=True, provenance=provenance(),
        geometry=dict(compute=len(geometry.compute_xy), memory=len(geometry.memory_xy),
                      cm_edges=graph.number_of_edges(), cc_edges=0, mm_edges=0,
                      structural_components=nx.number_connected_components(graph),
                      example_cc_structural_path=nx.shortest_path(graph, 'C0', 'C1'),
                      structural_paths_are_executable=False),
        direct_routes_checked={name:sum(map(len, f.paths.values())) for name,f in fabrics.items()},
        nonneighbor_probe=dict(compute=0, memory=remote,
            structural_path=nx.shortest_path(graph,'C0',f'M{remote}'),
            fixed_byte_service_tb_s=no_floor['served_tb_s'][0], floor_one_feasible=floor['feasible']),
        read_probe=dict(evidence='synthetic', delivered_words=224, memory_words=dict(targets),
                        every_word_has_one_cm_edge=True, audit=result['audit']),
        dependency_probe=dict(link_latencies_tested=[1,100], makespans=[r['makespan_slots'] for r in dependencies],
                              interpretation='Ordering only; no message bytes or transfer latency'),
        source_hashes={p:sha256(Path(p).read_bytes()).hexdigest() for p in paths},
        scope='Direct fixed-residency memory reads only; no compute-to-compute forwarding or MoE dispatch/combine')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = audit()
    Path(args.output).write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('geometry','nonneighbor_probe','dependency_probe')}, indent=2))


if __name__ == '__main__':
    main()
