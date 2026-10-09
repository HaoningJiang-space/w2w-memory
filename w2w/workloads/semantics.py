"""Logical task work independent of physical weight residency; no runner imports."""
from dataclasses import asdict


def logical_work(graph):
    graph=asdict(graph) if not isinstance(graph,dict) else graph
    return dict(tasks=[dict(**{k:v for k,v in t.items() if k!='reads'},
                            weight_bytes=sum(r['size_bytes'] for r in t['reads']))
                       for t in graph['tasks']],data=graph['data'],control=graph['control'])
