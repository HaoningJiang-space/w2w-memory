"""Small open DSE: geometry x nonuniform exposure x widths x offline layout."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
from bank_sharing import geometry,templates,scenarios
from guaranteed_service_exchange import (contoured_geometry,balanced_assignment,Channels,
    ExposureFabric,StripedLayout,FixedService,FreePlacementService)
from memory_fabric_dse import FractionalLayout,project_static_layout,mutate_mask,bandwidth_moves
from run_gate0 import provenance


def run(output):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').exists():raise ValueError('Fresh output required')
    start=time.monotonic()
    def save(name,obj):(out/name).write_text(json.dumps(obj,indent=2,allow_nan=False))
    placements={m:geometry(m) for m in ('aligned','half_shifted_x','half_shifted')};placements['contoured']=contoured_geometry()
    training=scenarios(placements['contoured'],[300,301],fractions=(.25,.5),patterns=('uniform','clustered','correlated'))
    testing=scenarios(placements['contoured'],range(4000,4006))
    manifest=dict(provenance=provenance(),train_seeds=[300,301],test_seeds=list(range(4000,4006)),
        minimum_service_profiles=[0.,.9,1.],train_cases=len(training),test_cases=len(testing),
        algorithm='Finite seeds + one round short-wire edge additions/removals and 1000-bit port transfers; no global optimality claim',
        layout='Fixed home or L1 projected static bytes (design floor 0.9/1); continuous striping limit, no runtime remap',
        cost_scope='Repeated bank-port wires, data width and circuit proxies; different contour area remains reported',
        selection_budgets=dict(wire_mm=[800,1000,1400],connections=[64,160],max_total_port_bits=32000),
        oracle='Free-residency service bound, migration cost ignored; NOT an implemented runtime')
    save('manifest.json',manifest)
    save('scenarios.json',dict(training=[s.serializable() for s in training],testing=[s.serializable() for s in testing]))
    candidates=[];cache={};problems={};layouts={};fabrics={};design_maps={}
    def evaluate(method,mask,widths,stage,inherited=None):
        key=(method,tuple(mask),tuple(widths))
        if key in cache:return cache[key]
        identifier='d'+str(len(candidates)).zfill(3)
        fabric=ExposureFabric(placements[method],mask,Channels(tuple(widths)))
        maps={'fixed_home':StripedLayout.home(fabric)}
        if inherited:
            maps.update({'inherited_'+name:layout for name,layout in inherited.items() if name!='fixed_home'})
        for h in (.9,1.):
            mapped=project_static_layout(fabric,training,h,True)
            if mapped is not None:maps['static_joint_h'+str(h)]=mapped
        # A constructive reciprocal seed is another legal offline mapping, not
        # a restriction on the graph family. Bank degrees elsewhere vary 1..5.
        if method=='contoured' and all(len(ps)==2 and 0 in ps for ps in mask):
            for beta in (.125,.25,.5):
                try:maps['static_balanced_'+str(beta)]=StripedLayout.reciprocal(fabric,beta)
                except ValueError:pass
        profiles=[]
        for mode,layout in maps.items():
            layout=FractionalLayout(layout.shares)
            model=FixedService(fabric,layout)
            layout_id=identifier+'_'+mode
            layouts[layout_id]=layout;problems[layout_id]=model
            save(layout_id+'.shares.json',layout.shares.tolist())
            for floor in (0.,.9,1.):
                full=model.full_load_certificate(floor if floor else 1.)
                if floor and not full['feasible']:
                    profiles.append(dict(mode=mode,floor=floor,feasible=False));continue
                rates=[model.solve(s.demand,minimum=floor)['tb_s_per_active'] for s in training]
                profiles.append(dict(mode=mode,floor=floor,feasible=True,training_mean=float(np.mean(rates)),layout_id=layout_id,
                    layout_hash=layout.sha256,full_load_1_feasible=model.full_load_certificate()['feasible']))
        row=dict(id=identifier,method=method,stage=stage,mask=[list(ps) for ps in mask],widths=list(widths),
            bank_degree=[len(ps) for ps in mask],cost=fabric.cost(),profiles=profiles)
        candidates.append(row);cache[key]=row;fabrics[identifier]=fabric;design_maps[identifier]=maps
        print('DESIGN',identifier,method,stage,'profiles',sum(x['feasible'] for x in profiles),flush=True)
        save('candidates.json',candidates)
        return row
    for method,physical in placements.items():
        if method=='contoured':
            sparse=balanced_assignment(physical,(2,3))
            masks=[tuple((0,) for _ in range(32)),sparse,balanced_assignment(physical,(1,4)),balanced_assignment(physical,(1,2,3,4)),
                   tuple(tuple(range(5)) if b<8 else sparse[b] for b in range(32)),tuple(tuple(range(5)) for _ in range(32))]
            widths=[(8000,6000,6000,6000,6000),(8000,0,12000,12000,0)]
        else:
            private=templates(1)[0][1];sparse=dict(templates(2))['xor_1' if method!='half_shifted' else 'star_0']
            masks=[private,sparse,tuple(tuple(range(4)) if b<8 else private[b] for b in range(32)),templates(4)[0][1]]
            widths=[(8000,)*4,(4000,4000,12000,12000)]
        for mask in masks:
            for q in widths:evaluate(method,mask,q,'seed')
    # One local-search round per placement; choose a seed using TRAINING ONLY.
    for method,physical in placements.items():
        eligible=[(profile['training_mean'],row,profile) for row in candidates if row['method']==method and row['stage']=='seed'
                  for profile in row['profiles'] if profile['feasible'] and profile['floor']==.9 and row['cost']['bank_port_connections']<=64]
        if not eligible:continue
        _,seed,_=max(eligible,key=lambda x:(x[0],-x[1]['cost']['wire_mm']))
        mask=tuple(tuple(ps) for ps in seed['mask']);q=tuple(seed['widths'])
        for mutated in mutate_mask(mask,physical,limit=4):evaluate(method,mutated,q,'edge_move',design_maps[seed['id']])
        # Deterministic subset spans bandwidth transfer; not test-driven.
        for moved in list(bandwidth_moves(q))[::max(1,len(q)-1)][:4]:evaluate(method,mask,moved,'width_move',design_maps[seed['id']])
    selection=[]
    for floor in (0.,.9,1.):
        for wire in manifest['selection_budgets']['wire_mm']:
            for edges in manifest['selection_budgets']['connections']:
                for scope in ['joint']+list(placements):
                    choices=[(row,profile) for row in candidates if (scope=='joint' or row['method']==scope) and row['cost']['wire_mm']<=wire+1e-9 and row['cost']['bank_port_connections']<=edges
                             for profile in row['profiles'] if profile['feasible'] and profile['floor']==floor]
                    if not choices:
                        selection.append(dict(scope=scope,floor=floor,wire=wire,connections=edges,feasible=False));continue
                    row,profile=min(choices,key=lambda x:(-round(x[1]['training_mean'],9),x[0]['cost']['wire_mm'],x[0]['cost']['bank_port_connections'],x[0]['id'],x[1]['mode']))
                    selection.append(dict(scope=scope,wire=wire,connections=edges,id=row['id'],method=row['method'])|profile)
    save('selection.json',selection) # freeze before test; never reselect on test
    cases={(s['id'],s['layout_id'],s['floor']) for s in selection if s['feasible']}
    # Always retain the same-fabric FIXED mapping comparison for each winner.
    cases|={(identifier,identifier+'_fixed_home',floor) for identifier,layout_id,floor in list(cases)}
    count=0
    with (out/'records.jsonl').open('w') as stream:
        for identifier,layout_id,floor in sorted(cases):
            model=problems[layout_id];oracle=FreePlacementService(fabrics[identifier])
            full=model.full_load_certificate(floor if floor else 1.)
            if floor and not full['feasible']:continue
            full_demand=model.solve(np.full(36,4.),minimum=floor)
            for phase in testing:
                t=model.solve(phase.demand,minimum=floor)
                common=model.solve(phase.demand,minimum=floor,objective='common')
                upper=oracle.solve(phase.demand,minimum=floor)
                assert t['total_tb_s']<=upper['total_tb_s']+1e-7
                potential=min(float(phase.demand.sum()),36.)
                # Capacity-minus-served is an unmet-demand bound gap, not all
                # idle bandwidth: idle service may exceed remaining demand.
                row=dict(id=identifier,method=next(c['method'] for c in candidates if c['id']==identifier),layout_id=layout_id,
                    floor=floor,layout_hash=layouts[layout_id].sha256,pattern=phase.pattern,fraction=phase.fraction,seed=phase.seed,
                    throughput=t,common=common,oracle=upper,full_load_service=full_demand,
                    demand_limited_pool_bound_tb_s=potential,unrecovered_bound_tb_s=potential-t['total_tb_s'],
                    fixed_layout_gap_tb_s=upper['total_tb_s']-t['total_tb_s'])
                stream.write(json.dumps(row,allow_nan=False)+'\n');count+=1
            stream.flush();print('TEST',identifier,layout_id,floor,count,round(time.monotonic()-start,1),flush=True)
    manifest.update(candidates=len(candidates),records=count,elapsed_seconds=time.monotonic()-start,
        records_sha256=hashlib.sha256((out/'records.jsonl').read_bytes()).hexdigest())
    save('manifest.json',manifest);print('COMPLETE',count,round(manifest['elapsed_seconds'],1),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();run(a.output)
