#!/usr/bin/env python3
"""Read-only fixed-route tensor sharing opportunity; no multicast execution.

Payload path unions are accounting bounds. They exclude packet/control costs,
finite branch state, temporal consumer eligibility and adaptive routing.
"""
import argparse,hashlib,json,platform,subprocess,sys
from dataclasses import asdict
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))


def measure(spec,graph,metadata):
    from w2w.system.builder import SystemBuilder
    builder=SystemBuilder(spec).validate_graph(graph)
    edges={e.id:e for e in graph.data};tasks={t.id:t for t in graph.tasks};seen=set();groups={}
    for row in metadata['physical_copies']:
        if row['id'] in seen or row['id'] not in edges:raise ValueError('Unmatched/repeated tensor copy')
        seen.add(row['id']);edge=edges[row['id']]
        if (row['source'],row['destination'],row['bytes'])!=(tasks[edge.producer].tile,tasks[edge.consumer].tile,edge.size_bytes):
            raise ValueError('Tensor copy changes actual graph placement or payload')
        identity=(row['tensor'],row['storage_id'],edge.producer,row['source'],row['bytes'])
        route=builder.route(row['source'],row['destination'])
        groups.setdefault(identity,[]).append((row['id'],tuple(route)))
    if seen!=set(edges):raise ValueError('Missing materialized execution copy')
    details=[]
    for identity,copies in sorted(groups.items()):
        tensor,storage,producer,source,size=identity
        per_copy=sum(len(route) for _,route in copies)*size
        union=len({link for _,route in copies for link in route})*size
        if union>per_copy:raise ValueError('Invalid fixed-path union bound')
        details.append(dict(tensor=tensor,storage_id=storage,producer=producer,source=source,bytes=size,
            consumers=len(copies),unicast_payload_byte_hops=per_copy,union_payload_byte_hops=union))
    return dict(materialized_copies=len(seen),logical_groups=len(groups),
        fanout_groups=sum(r['consumers']>1 for r in details),
        unicast_payload_byte_hops=sum(r['unicast_payload_byte_hops'] for r in details),
        union_payload_byte_hops=sum(r['union_payload_byte_hops'] for r in details),groups=details)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);args=parser.parse_args()
    if platform.node()!='ee4e072' or args.output.exists() or not args.output.is_absolute():
        raise ValueError('Fresh hn072 output required')
    from w2w.experiments.run_static_placement import inputs
    cases={};fixed=None;input_hashes={}
    for policy in ('reference','balanced','hybrid'):
        spec,graph,_,data=inputs(policy,'cold')
        invariant=dict(data=[asdict(e) for e in graph.data],tasks=[asdict(t) for t in graph.tasks],
            control=[asdict(e) for e in graph.control],physical=asdict(spec.stack),network=data['network_policy'])
        if fixed is not None and fixed!=invariant:raise ValueError('Memory policy also changed compute/fabric execution')
        fixed=invariant;cases[policy]=measure(spec,graph,data['metadata'])
        input_hashes[policy]=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    if len({json.dumps(row,sort_keys=True) for row in cases.values()})!=1:
        raise ValueError('Activation path accounting unexpectedly depends on memory placement')
    files=['tools/audit_fabric_fanout.py','w2w/mapping/lowering.py','w2w/domain/execution.py',
        'w2w/experiments/run_static_placement.py','configs/workloads/c0_b1.json','configs/machine/v3-small.json']
    result=dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        source_hashes={f:hashlib.sha256((REPO/f).read_bytes()).hexdigest() for f in files},
        input_hashes=input_hashes,cases=cases,
        scope='fixed-route payload-only fanout accounting; not actual adaptive hop-flits or a feasible multicast protocol',
        interpretation='all three memory layouts have the same activation sharing opportunity; timing, contention and ranking remain untested under multicast')
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:{n:v for n,v in r.items() if n!='groups'} for k,r in cases.items()}))


if __name__=='__main__':main()
