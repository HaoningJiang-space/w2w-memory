from w2w.paths import REPO_ROOT
"""Archive audit: reconstruct frozen layouts and summarize paired outcomes."""
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from w2w.service.matching_placement import contoured
from w2w.synthesis.cycle_configurations import Configuration,assemble,primal_audit


def main():
    root=REPO_ROOT
    certificate=(root/'artifacts/results/cycles/cycle_construction_certificate.json').read_bytes()
    cert=json.loads(certificate)
    compressed=(root/'artifacts/results/cycles/cycle_configuration_results.json.gz').read_bytes()
    raw=gzip.decompress(compressed);results=json.loads(raw)
    assert cert['passed'] and not cert['smoke'] and not cert['dirty']
    assert cert['commit']==results['commit']
    assert hashlib.sha256(certificate).hexdigest()==results['certificate_sha256']
    physical={pitch:contoured(pitch) for pitch in (25.6,25.7)}
    rows=[]
    for d in results['designs']:
        p=physical[d['pitch']];qs=[];choices=[]
        for record in d['selected']:
            q=Configuration.build(p,record['cycle']);assert q is not None
            assert list(q.compute)==record['compute'] and list(q.memory)==record['memory']
            qs.append(q);choices.append(dict(ratio=record['ratio']))
        a=assemble(qs,choices,list(range(len(qs))))
        assert hashlib.sha256(a.tobytes()).hexdigest()==d['layout_sha256']
        assert np.count_nonzero(a)==72
        primal_audit(p,a,np.ones(36),range(36))
        assert d['solver']['gap']==0 and d['minimum_service']>=1-1e-8
        assert abs(np.mean(d['test_means'])-d['test_mean'])<1e-12
        rows.append({k:d[k] for k in ('pitch','kind','maximum','catalog_size','component_counts','training_mean',
            'test_mean','common_mean','worst_sample_mean','minimum_service','p5_mean','resource_residual')})
    comparisons=[]
    for item in results['comparisons']:
        a=next(d for d in results['designs'] if d['pitch']==item['pitch'] and d['kind']==item['kind'] and d['maximum']==2)
        b=next(d for d in results['designs'] if d['pitch']==item['pitch'] and d['kind']==item['kind'] and d['maximum']==item['maximum'])
        diff=np.array(b['test_means'])-a['test_means'];cdiff=np.array(b['test_common'])-a['test_common']
        assert abs(diff.mean()-item['delta'])<1e-12
        comparisons.append(dict(item,regressing_sample_fraction=float(np.mean(diff < -1e-9)),
            worst_sample_delta=float(diff.min()),common_regressing_sample_fraction=float(np.mean(cdiff < -1e-9))))
    report=dict(source_commit=results['commit'],certificate_sha256=hashlib.sha256(certificate).hexdigest(),
        raw_result_sha256=hashlib.sha256(raw).hexdigest(),compressed_result_sha256=hashlib.sha256(compressed).hexdigest(),
        construction_checks=cert['checks'],master_bruteforce=cert['master_bruteforce'],
        local_service_lp_total=cert['checks']['throughput_lp']+cert['checks']['common_lp'],
        global_service_lp_total=sum(2*len(d['lp_checks']) for d in results['designs']),
        all_test_resource_states=sum(len(d['test_means']) for d in results['designs']),
        largest_global_lp_rate_error=max(x['max_rate_error'] for d in results['designs'] for x in d['lp_checks']),
        verification_elapsed_s=cert['elapsed_s'],experiment_elapsed_s=results['elapsed_s'],
        rows=rows,comparisons=comparisons)
    (root/'artifacts/results/cycles/cycle_gate_summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','comparisons')},indent=2))


if __name__=='__main__':main()
