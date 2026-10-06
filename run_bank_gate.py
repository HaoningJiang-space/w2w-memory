"""One narrow Gate: repeated sparse bank-port graphs with frozen page layouts."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from bank_sharing import (BANKS,PORTS,PAGES,DATA_GIB,PAGE_GIB,BANK_GIB,
    BankFabric,PoolingNetwork,geometry,templates,scenarios,search_templates,
    periodic_reference,interior_scenario)
from run_gate0 import provenance


def legacy_cut_audit(path):
    data=json.loads(Path(path).read_text())
    physical=geometry('half_shifted')
    network=PoolingNetwork(BankFabric(physical,templates(4)[0][1]))
    results=[]
    for row in data['records']:
        if (row['diameter_mm']==300 and row['method']=='half_shifted' and row['bank_mode']=='pooled'
            and row['hb_tb_s']==4 and row['controller_tb_s']==4 and row['pool_port_fraction']==1
            and row['objective']=='throughput' and row['workload'] in ('random_0.25','random_0.5','clustered_quarter','full')):
            cut=network.evaluate(row['demand_tb_s'])
            if abs(cut['oracle_tb_s']-row['total_tb_s'])>1e-7:raise RuntimeError('Legacy LP/min-cut mismatch')
            results.append(dict(workload=row['workload'],seed=row['seed'],active=row['active'],
                                legacy_tb_s=row['total_tb_s'],**cut))
    if len(results)!=22:raise ValueError('Expected 22 old reference records')
    return results


def run(output,seed_count,legacy,placements):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    if (out/'records.jsonl').exists():raise ValueError('Use a fresh result directory')
    train_ids=[0,1];test_ids=list(range(100,100+seed_count))
    assert not set(train_ids)&set(test_ids)
    manifest=dict(provenance=provenance(),train_seeds=train_ids,test_seeds=test_ids,
                  banks=BANKS,hb_regions=PORTS,pages_per_compute=PAGES,data_gib_per_compute=DATA_GIB,
                  page_gib=PAGE_GIB,bank_gib=BANK_GIB,placements=placements,
                  scope='Finite 6x6 rectangle inside 300mm circle; boundary diagnostic holds finite templates/layouts fixed',
                  oracle='Free-bank-service relaxation, ignores data residency; not executable placement',
                  sharing_site='Memory-side digital bank-output selection/arbitration before HB',
                  legacy_cut_audit=legacy_cut_audit(legacy))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    designs=[];count=0;start=time.monotonic()
    with (out/'records.jsonl').open('w') as records:
        for method in placements:
            physical=geometry(method)
            training=scenarios(physical,train_ids,fractions=(.25,.5))
            heldout=scenarios(physical,test_ids)
            ideal=BankFabric(physical,templates(4)[0][1])
            # Strictly frozen across k: home and conventional geometry-aware stripe.
            frozen={mode:ideal.plan_layout(mode) for mode in ('home_striped','static_interleaved')}
            for mode in ('home_striped','static_interleaved','static_train_greedy','oracle'):
                for k in (1,2,4):
                    fabric,layout,search=search_templates(physical,k,mode,training,frozen.get(mode))
                    identifier=f'{method}_{mode}_k{k}'
                    design=dict(id=identifier,method=method,layout_mode=mode,k=k,search=search,
                                layout_hash=None if layout is None else fabric.layout_hash(layout),
                                bank_storage_gib=None if layout is None else fabric.validate_layout(layout).tolist())
                    if layout is not None:
                        design['layout_file']=identifier+'.layout.json'
                        (out/design['layout_file']).write_text(json.dumps(layout.tolist()))
                    designs.append(design)
                    (out/'designs.json').write_text(json.dumps(designs,indent=2))
                    scopes=[('finite',physical,heldout)]
                    diagnostic=[s for s in heldout if s.pattern=='uniform' and s.fraction in (.25,1.) and s.seed<103]
                    scopes.append(('interior_active',physical,[interior_scenario(s,physical) for s in diagnostic]))
                    scopes.append(('periodic_reference',periodic_reference(physical),diagnostic))
                    for scope,phases_physical,phases in scopes:
                        current=BankFabric(phases_physical,fabric.mask)
                        network=PoolingNetwork(current);compiled={}
                        for phase in phases:
                            key='oracle' if layout is None else phase.weights.tobytes()
                            if key not in compiled:compiled[key]=current.compile(layout,phase.weights)
                            problem=compiled[key]
                            throughput=problem.solve(phase.demand)
                            common=problem.solve(phase.demand,'common')
                            cut=network.evaluate(phase.demand)
                            if throughput['total_tb_s']>cut['oracle_tb_s']+1e-7:raise RuntimeError('Fixed data exceeds flow relaxation')
                            if layout is None and abs(throughput['total_tb_s']-cut['oracle_tb_s'])>1e-7:raise RuntimeError('LP/flow disagree')
                            if layout is not None and current.layout_hash(layout)!=design['layout_hash']:raise RuntimeError('Runtime data migration')
                            row=dict(design_id=identifier,scope=scope,method=method,k=k,layout_mode=mode,
                                     pattern=phase.pattern,fraction=phase.fraction,seed=phase.seed,
                                     active=int(np.count_nonzero(phase.demand)),demand_tb_s=phase.demand.tolist(),
                                     throughput=throughput,common=common,cut=cut,
                                     pooling_efficiency=throughput['total_tb_s']/cut['global_pooling_bound_tb_s'],
                                     layout_hash=design['layout_hash'])
                            records.write(json.dumps(row,allow_nan=False)+'\n');count+=1
                    records.flush()
                    print(identifier,'selected',search['selected']['name'],'records',count,
                          'seconds',round(time.monotonic()-start,1),flush=True)
    manifest.update(records=count,elapsed_seconds=time.monotonic()-start)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print('COMPLETE',count,'records',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--seeds',type=int,default=10)
    p.add_argument('--legacy',default='memory_results/eex005_gate/memory.json')
    p.add_argument('--placements',nargs='+',default=['aligned','half_shifted_x','half_shifted'])
    a=p.parse_args()
    if a.seeds<1:p.error('--seeds must be positive')
    run(a.output,a.seeds,a.legacy,a.placements)
