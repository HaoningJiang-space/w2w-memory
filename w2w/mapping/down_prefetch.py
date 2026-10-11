"""Bounded whole-matrix foil: fetch eligibility differs from mathematical start."""
from dataclasses import dataclass, asdict
from w2w.common.fingerprints import digest_read_v1


@dataclass(frozen=True)
class DownFetchRelease:
    task: str
    fetch_predecessors: tuple[str,...]
    demand_tasks: tuple[str,str]


@dataclass(frozen=True)
class DownPrefetchPlan:
    graph_sha256: str
    releases: tuple[DownFetchRelease,...]
    waiting_down_per_cluster: int = 1
    metadata_bytes_per_cluster: int = 8
    policy: str = 'whole-down-spare-slot-v1'


def whole_matrix_down_prefetch(graph):
    tasks={t.id:t for t in graph.tasks};pred={k:set() for k in tasks}
    for e in (*graph.data,*graph.control):pred[e.consumer].add(e.producer)
    rows=[]
    for key,t in sorted(tasks.items()):
        if not key.endswith('/down'):continue
        if not t.stream or not t.reads:raise ValueError('Down must have explicit whole-matrix weight service')
        gate,up=key[:-4]+'gate',key[:-4]+'up'
        if gate not in tasks or up not in tasks or gate in pred[up]:
            raise ValueError('Bounded foil requires independent S1 Gate/Up')
        dependencies=tuple(sorted(pred[gate]|pred[up]))
        if key in dependencies or gate in dependencies or up in dependencies:
            raise ValueError('Invalid projection fetch dependency')
        rows.append(DownFetchRelease(key,dependencies,(gate,up)))
    if not rows:raise ValueError('No complete gated FFN block')
    return DownPrefetchPlan(digest_read_v1(asdict(graph)),tuple(rows))
