"""Independent pair-population check of all integrated service results."""
import argparse
import json
from pathlib import Path


def check(path):
    d=json.loads(Path(path).read_text())
    peer={a:b for pair in d['pairs'] for a,b in (pair,pair[::-1])}
    traces={(r['output_bits'],r['depth'],len(r['active']),r['policy']):r for r in d['micro']}
    error=0.
    for r in d['wafer']:
        active=set(r['active']);n=len(active)
        alone=sum(peer[c] not in active for c in active);fraction=alone/n
        alpha=r['alpha']
        expected={'legacy_tb_s':1+fraction,
            'fixed_partition_tb_s':2*min(alpha,1/3),
            'direct_envelope_tb_s':alpha*(1+fraction),
            'buffered_envelope_tb_s':2*alpha*fraction+min(1,2*alpha)*(1-fraction)}
        rates={}
        for count in (1,2):
            t=traces[r['bits'],r['depth'],count,r['policy']]
            rates[count]=2*min(t['rate_per_native'][:count])
        expected['executed_tb_s']=rates[1]*fraction+rates[2]*(1-fraction)
        expected['common_tb_s']=min([rates[1]]*(alone>0)+[rates[2]]*(alone<n))
        for field,value in expected.items():
            difference=abs(r[field]-value);error=max(error,difference)
            assert difference<1e-8,(field,r,value)
        assert r['floor_one_feasible']==(expected['common_tb_s']>=1-1e-9)
        assert r['layout_hash']==d['layout_hash']
    print('INDEPENDENT PAIR CHECK',len(d['wafer']),'rows; max error',error)
    for alpha in (.5,.75,1.):
        for depth in (0,1,2,8):
            rows=[r for r in d['wafer'] if r['alpha']==alpha and r['depth']==depth and r['policy']=='round_robin']
            print(alpha,depth,{r['scenario']:round(r['executed_tb_s'],6) for r in rows})
    print('CONVERGENCE',d['convergence'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input');a=p.parse_args();check(a.input)
