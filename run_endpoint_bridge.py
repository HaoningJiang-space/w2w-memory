"""One frozen full-bank pair layout, endpoint envelopes and finite execution."""
import argparse
from functools import lru_cache
import json
import platform
import subprocess
from pathlib import Path
import numpy as np
from bank_sharing import BANKS, BANK_BW
from guaranteed_service_exchange import contoured_geometry, ExposureFabric, Channels, FixedService
from service_driven_fabric import paired_layout
from endpoint_execution import execute, EndpointFixedService


def run(output, slots=8192):
    if subprocess.check_output(['git','status','--porcelain'],text=True).strip():
        raise RuntimeError('Commit source before experiment')
    physical=contoured_geometry()
    fabric=ExposureFabric(physical,tuple((0,2,3) for _ in range(BANKS)),
                          Channels((8000,0,8000,8000,0)))
    layout,matching=paired_layout(fabric)
    assert matching['matched_clients']==36
    peer={a:b for pair in matching['pairs'] for a,b in (pair,pair[::-1])}
    pairs=matching['pairs'];rng=np.random.default_rng(620100)
    active_sets={'single':[pairs[0][0]],'one_pair':pairs[0],
                 'random9':sorted(rng.choice(36,9,replace=False).tolist()),
                 'first9':list(range(9)),'full':list(range(36))}
    @lru_cache(None)
    def trace(bits,depth,count,policy='round_robin',duration=slots):
        return execute(bits,depth,tuple(range(count)),policy=policy,slots=duration,warmup=1024)
    micro=[]
    for bits in (64,128,192,256):
        for depth in (0,1,2,8):
            for count in (1,2):
                for policy in ('round_robin','ordered'):
                    micro.append(trace(bits,depth,count,policy))
    rows=[]
    for bits in (64,128,192,256):
        alpha=bits/256
        envelope={name:EndpointFixedService(fabric,layout,name,alpha)
                  for name in ('fixed_share','direct','buffered_envelope')}
        for name,active in active_sets.items():
            demand=np.zeros(36);demand[active]=4
            old=FixedService(fabric,layout).solve(demand,minimum=0)
            env={k:v.solve(demand,minimum=0) for k,v in envelope.items()}
            for depth in (0,1,2,8):
                for policy in ('round_robin','ordered'):
                    caps={}
                    for m in range(36):
                        users=[c for c in (m,peer[m]) if c in active]
                        if not users:continue
                        measured=trace(bits,depth,len(users),policy)
                        # Both memories in a pair execute identical symmetric schedules.
                        # Use the lower rate if the finite observation ends mid-period.
                        rate=min(measured['rate_per_native'][:len(users)])*BANK_BW
                        for c in users:
                            for b in range(BANKS):caps[c,m*BANKS+b]=rate
                    base=envelope['direct' if depth==0 else 'buffered_envelope']
                    replay=base.with_delivered_caps(caps)
                    solved=replay.solve(demand,minimum=0)
                    common=replay.solve(demand,minimum=0,objective='common')
                    floor=replay.solve(demand,minimum=1)
                    # Independently construct full-byte path flows from measured rates.
                    witness=np.zeros(replay.nvar)
                    witness[:36]=solved['served_tb_s']
                    for col,c,bank,edge in replay.route_variables:
                        witness[col]=layout.shares[c,bank]*witness[c]
                        assert witness[col]<=caps.get((c,bank),0)+1e-9
                    residual=max(0.,float(np.max(replay.ub@witness-replay.fabric.limits)),
                                 float(np.max(np.abs(replay.eq@witness))))
                    assert residual<1e-8
                    # Each reticle's 32 bank engines are in lockstep. Each selected
                    # physical port can carry >=1 TB/s; instantaneous offered output
                    # is <= alpha*1 TB/s, controller sees at most two such ports.
                    for c in active:
                        for m in (c,peer[c]):
                            route=fabric.paths[c,m*BANKS]
                            assert len(route)==1
                            assert fabric.limits[fabric.row['hb_edge',route[0]]]>=alpha-1e-9
                    rows.append(dict(bits=bits,alpha=alpha,depth=depth,policy=policy,
                        scenario=name,active=active,layout_hash=layout.sha256,
                        legacy_tb_s=old['tb_s_per_active'],
                        fixed_partition_tb_s=env['fixed_share']['tb_s_per_active'],
                        direct_envelope_tb_s=env['direct']['tb_s_per_active'],
                        buffered_envelope_tb_s=env['buffered_envelope']['tb_s_per_active'],
                        executed_tb_s=solved['tb_s_per_active'],
                        common_tb_s=4*common['common_fraction'],floor_one_feasible=floor['feasible'],
                        witness_residual=residual,
                        endpoint_storage_bits_per_memory=(BANKS*256 if depth==0 else BANKS*3*depth*256),
                        exported_lane_bits_per_memory=BANKS*3*bits))
    convergence=[]
    for bits,depth,count,policy in ((128,1,2,'round_robin'),(128,1,2,'ordered'),
                                    (128,8,2,'ordered'),(192,2,1,'round_robin')):
        short=trace(bits,depth,count,policy)
        long=trace(bits,depth,count,policy,slots*2)
        convergence.append(dict(bits=bits,depth=depth,count=count,policy=policy,
            short=short['total_per_native'],long=long['total_per_native'],
            difference=long['total_per_native']-short['total_per_native']))
    result=dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        host=platform.node(),scope='One frozen k3 pair layout; complete-word digital execution, not DRAM timing or PPA',
        layout_hash=layout.sha256,pairs=pairs,active_sets=active_sets,
        physical_cost=fabric.cost(),native_word_bits=256,
        native_slot_ns=256/(BANK_BW*8000),slots=slots,warmup=1024,
        micro=micro,wafer=rows,convergence=convergence)
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2)+'\n')
    print('VERIFIED',len(micro),'finite traces;',len(rows),'wafer replays;',layout.sha256)
    for r in rows:
        if r['scenario'] in ('random9','full') and r['policy']=='round_robin':
            print(r['alpha'],r['depth'],r['scenario'],round(r['executed_tb_s'],6),r['floor_one_feasible'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--slots',type=int,default=8192)
    a=p.parse_args();run(a.output,a.slots)
