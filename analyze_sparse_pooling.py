"""Reconstruct frozen layouts and reproduce paired statistics from raw results."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from matching_placement import contoured,mixture,ReticleService
from cycle_configurations import Configuration,primal_audit
from run_cycle_configuration_gate import activity_sets,KINDS
from sparse_pooling import factor_certificate,matching_candidates,layout_summary


def main():
    parser=argparse.ArgumentParser();parser.add_argument('input');parser.add_argument('--output',required=True)
    args=parser.parse_args();path=Path(args.input)
    raw=gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_bytes()
    data=json.loads(raw);p=contoured();service=ReticleService(p)
    candidates={v['name']:v for v in matching_candidates(p)}
    tests=activity_sets(range(data['test_seeds'][0],data['test_seeds'][1]+1))
    edges={(e['c'],e['m']) for e in p.edges}
    for certificate in data['factor_certificates']:
        rebuilt=factor_certificate(36,edges,certificate['degree'])
        assert rebuilt['flow']==certificate['flow']==certificate['cut_capacity']
        # Validate the archived cut itself, independently of the returned partition.
        left=set(certificate['source_side']);d=certificate['degree']
        value=sum(d for c in range(36) if c not in left)
        value+=sum(1 for c,m in edges if c in left and 36+m not in left)
        value+=sum(d for m in range(36) if 36+m in left)
        assert 's' in left and 't' not in left and value==certificate['flow']
    summary=dict(source_commit=data['commit'],host=data['host'],raw_sha256=hashlib.sha256(raw).hexdigest(),
        train_seeds=data['train_seeds'],test_seeds=data['test_seeds'],rows=[],comparisons=[],
        explicit_checks=sum(2*len(r['explicit_lp_checks']) for r in data['designs']),
        max_explicit_lp_error=max(e for r in data['designs'] for check in r['explicit_lp_checks'] for e in check['errors']),
        max_resource_residual=max(r['max_resource_residual'] for r in data['designs']))
    local_checks=0;local_error=0.
    for r in data['designs']:
        if r['name']=='pair':a=mixture([list(range(36)),[c^1 for c in range(36)]],[.5,.5])
        elif r['name']=='cycle_up_to4':
            a=sum((Configuration.build(p,v['cycle']).matrix(v['ratio'],36) for v in r['selection']['selected']),start=np.zeros((36,36)))
        else:a=candidates[r['selection']['selected']['name']]['layout']
        assert np.array_equal(a,np.array(r['layout']))
        assert hashlib.sha256(a.tobytes()).hexdigest()==r['layout_sha256']
        primal_audit(p,a,np.ones(36),range(36))
        for index in (0,1,2,3):
            active=np.flatnonzero(tests[r['kind']][index])
            for objective,key in [('throughput','test_means'),('common','test_common')]:
                result=service.solve(a,active,objective,floor=1)
                assert result['feasible']
                error=abs(result['mean']-r[key][index]);assert error<1e-8
                local_error=max(local_error,error);local_checks+=1
        assert abs(np.mean(r['test_means'])-r['test_mean'])<1e-12
        assert abs(np.mean(r['test_common'])-r['common_mean'])<1e-12
        summary['rows'].append({key:r[key] for key in ('kind','name','test_mean','common_mean','minimum_service','worst_sample_mean','layout_summary','full_load_common')})
    for kind in KINDS:
        rows={r['name']:r for r in data['designs'] if r['kind']==kind}
        for name in ('mixture3','mixture4'):
            for baseline in ('pair','cycle_up_to4'):
                row=rows[name];base=rows[baseline]
                delta=np.array(row['test_means'])-base['test_means']
                half=1.96*delta.std(ddof=1)/np.sqrt(len(delta))
                summary['comparisons'].append(dict(kind=kind,name=name,baseline=baseline,
                    relative_percent=100*(row['test_mean']/base['test_mean']-1),
                    delta=float(delta.mean()),paired_ci95=[float(delta.mean()-half),float(delta.mean()+half)],
                    fraction_worse=float(np.mean(delta < -1e-8))))
    summary.update(local_explicit_checks=local_checks,max_local_error=local_error)
    Path(args.output).write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({key:summary[key] for key in ('source_commit','raw_sha256','explicit_checks','max_explicit_lp_error','local_explicit_checks','max_local_error')},indent=2))


if __name__=='__main__':main()
