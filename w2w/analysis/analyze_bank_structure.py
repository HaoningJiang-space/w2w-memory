"""Exact uniform-active-set coverage expectation; no Monte Carlo or scheduling."""
from math import comb
import argparse
import json
from pathlib import Path
from w2w.constants import BANKS
from w2w.service.bank_sharing import BankFabric,circuit_cost,geometry,templates,periodic_reference


def analyze(output):
    records=[]
    for placement in ('aligned','half_shifted_x','half_shifted'):
        original=geometry(placement)
        for scope,physical in [('finite',original),('periodic_reference',periodic_reference(original))]:
            assert all(physical.edge_bandwidth(e)>=1.-1e-10 for e in physical.edges)
            assert all(len({e['m'] for e in physical.edges if e['c']==c})<=4 for c in range(36))
            for k in (1,2,4):
                for name,mask in templates(k):
                    fabric=BankFabric(physical,mask)
                    clients=[set() for _ in range(36*BANKS)]
                    for c,b in fabric.paths:clients[b].add(c)
                    degree=[len(s) for s in clients]
                    for active in (9,18,27,36):
                        probability=[1-(comb(36-d,active) if 36-d>=active else 0)/comb(36,active) for d in degree]
                        total=sum(probability)/BANKS
                        records.append(dict(method=placement,scope=scope,k=k,mask=name,active=active,
                            mean_oracle_tb_s=total,mean_oracle_tb_s_per_active=total/active,
                            bank_client_degree_histogram={str(d):degree.count(d) for d in set(degree)},
                            cost=circuit_cost(mask)))
    # With one distinct receiving compute per port on the XY torus, graph shape
    # cannot change the exact uniform-subset mean at fixed k.
    for k in (1,2,4):
        for active in (9,18,27,36):
            values=[r['mean_oracle_tb_s'] for r in records if r['method']=='half_shifted' and r['scope']=='periodic_reference' and r['k']==k and r['active']==active]
            assert max(values)-min(values)<1e-10
    Path(output).write_text(json.dumps(dict(
        assumptions='4 TB/s demand per active compute; 1 TB/s memory, >=1 TB/s per physical HB edge; <=4 neighboring memory reticles; free data residency',
        expression='E[BW]=sum_b mu_b*(1-choose(N-r_b,A)/choose(N,A)); r_b is number of distinct clients reaching bank b',
        records=records),indent=2))
    print('Exact expectations:',len(records))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output');analyze(p.parse_args().output)
