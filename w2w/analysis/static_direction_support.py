"""Apply the existing balanced-residency constraint to fixed template directions.

This is an aggregate native-capacity upper bound. It does not model mask
rotation legality, row timing, per-bank access wiring or endpoint capacities.
"""
import argparse
import json
from pathlib import Path

import networkx as nx
import numpy as np
from scipy.optimize import linprog

from w2w.provenance import provenance
from w2w.synthesis.provisioning_catalog import candidate_designs


def maximum_nonhome(support):
    support=np.asarray(support,dtype=bool)
    n=len(support)
    if support.shape!=(n,n) or not all(np.diag(support)):
        raise ValueError('Square support with one home per compute required')
    edges=list(zip(*np.nonzero(support)))
    eq=np.zeros((2*n,len(edges)))
    objective=[]
    for k,(c,m) in enumerate(edges):
        eq[c,k]=eq[n+m,k]=1
        objective.append(-int(c!=m))
    result=linprog(objective,A_eq=eq,b_eq=np.ones(2*n),bounds=(0,None),method='highs')
    if not result.success:
        raise ValueError('Native full-load assignment infeasible')
    graph=nx.DiGraph();graph.add_nodes_from(range(n));graph.add_edges_from((c,m) for c,m in edges if c!=m)
    acyclic=nx.is_directed_acyclic_graph(graph)
    mean=float(-result.fun/n)
    if acyclic and abs(mean)>1e-9:
        raise ValueError('Acyclic balanced nonhome flow must vanish')
    return dict(computes=n,nonhome_edges=len(graph.edges),acyclic=acyclic,
        maximum_mean_nonhome_fraction=mean,
        nontrivial_scc_sizes=sorted(len(c) for c in nx.strongly_connected_components(graph) if len(c)>1),
        equality_residual=float(abs(eq@result.x-1).max()))


def analyze():
    design=candidate_designs()[0]['b_cfg']
    n=len(design.geometry.compute_xy)
    if n!=36 or any(c!=m for c,m,_,p,_,_ in design.geometry.routes if p==0):
        raise ValueError('Expected current H/plus home identity')
    rows=[]
    for label,directions in (('all_direction_2',(2,)*n),('all_direction_3',(3,)*n),
                             ('frozen_pair_binding',design.shared_directions)):
        support=np.eye(n,dtype=bool)
        edges=[]
        for c,m,_,p,_,_ in design.geometry.routes:
            if p==directions[m] and c!=m:
                support[c,m]=True;edges.append([c,m,p])
        rows.append(dict(label=label,memory_directions=list(directions),edges=edges,**maximum_nonhome(support)))
    return dict(schema='w2w.static-direction-support.v1',provenance=provenance(),results=rows,
        scope='Existing balanced residency theory applied to fixed global directions; aggregate upper bound; '
              'does not exclude legal mask rotations, mixed-bank templates, altered home mapping or spare native capacity')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True)
    a=p.parse_args();result=analyze();Path(a.output).write_text(json.dumps(result,indent=2)+'\n')
    for r in result['results']:
        print(r['label'],r['nonhome_edges'],r['acyclic'],r['maximum_mean_nonhome_fraction'])
