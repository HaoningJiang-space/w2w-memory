"""Gate 1/2 synthetic service bounds. Run from repository root."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import numpy as np
from w2w.geometry.memory_model import Budgets,MemoryFabric,construct_memory_system
from w2w.provenance import provenance


def run(out, seeds):
    output=Path(out);output.mkdir(parents=True,exist_ok=True)
    records=[]; topologies=[]; skipped=[]
    for diameter in (200,300):
        for method in ('aligned','half_shifted_x','half_shifted','rotated'):
            system=construct_memory_system(dict(wafer_diameter=diameter,method=method),dict(reticle_size=(26.,33.)))
            try:
                MemoryFabric(system)
            except ValueError as e:
                skipped.append(dict(diameter=diameter,method=method,reason=str(e)));continue
            for mode in ('partitioned','pooled'):
                fabric=MemoryFabric(system,bank_mode=mode)
                topology=fabric.summary();topology['diameter_mm']=diameter;topologies.append(topology)
                n=len(fabric.compute)
                # Same row-major indices and seeds across the three matched designs.
                center=min(range(n),key=lambda i:fabric.compute[i].x**2+fabric.compute[i].y**2)
                for hb in (1.,2.,4.,8.):
                    for controller in (1.,4.):
                        for port_fraction in ((1.,) if mode=='partitioned' else (.25,.5,1.)):
                            budget=replace(Budgets(),compute_hb_tb_s=hb,memory_hb_tb_s=hb,
                                           controller_tb_s=controller,pool_port_fraction=port_fraction)
                            fabric.budgets=budget
                            workloads=[('full',0,np.full(n,4.)),('single_center',0,np.eye(n)[center]*4)]
                            # Clustered activity is often harder to balance than scattered activity.
                            order=sorted(range(n),key=lambda i:fabric.compute[i].x**2+fabric.compute[i].y**2)
                            clustered=np.zeros(n);clustered[order[:max(1,n//4)]]=4
                            workloads.append(('clustered_quarter',0,clustered))
                            for seed in range(seeds):
                                rng=np.random.default_rng(seed)
                                for fraction in (.25,.5):
                                    demand=np.zeros(n);demand[rng.choice(n,max(1,round(n*fraction)),replace=False)]=4
                                    workloads.append((f'random_{fraction}',seed,demand))
                            for workload,seed,demand in workloads:
                                for objective in ('throughput','fair'):
                                    result=fabric.solve(demand,objective)
                                    records.append(dict(diameter_mm=diameter,method=method,bank_mode=mode,
                                                        hb_tb_s=hb,controller_tb_s=controller,pool_port_fraction=port_fraction,
                                                        workload=workload,seed=seed,objective=objective,n_compute=n,n_memory=len(fabric.memory),
                                                        active=int(np.count_nonzero(demand)),demand_tb_s=demand.tolist(),**result))
                print(diameter,method,mode,'complete',flush=True)
    payload=dict(provenance=provenance(),assumptions='Direct-only read service, freely placeable data; no DRAM timing or migration cost',
                 seeds=seeds,topologies=topologies,records=records,skipped=skipped)
    (output/'memory.json').write_text(json.dumps(payload,indent=2,allow_nan=False))
    print('SOLVES',len(records),'SKIPPED',skipped,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='memory_results');p.add_argument('--seeds',type=int,default=10)
    a=p.parse_args()
    if a.seeds<1:p.error('--seeds must be positive')
    run(a.output,a.seeds)
