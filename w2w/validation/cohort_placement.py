"""Reconstruct every accepted owner swap without invoking the optimizer."""
import argparse
from hashlib import sha256
import gzip
import json
from pathlib import Path
import numpy as np

from w2w.provenance import provenance
from w2w.synthesis.cohort_placement import cohort_matrix, resource_matrix, score
from w2w.synthesis.provisioning_catalog import candidate_designs
from w2w.synthesis.provisioning_target import target_design


def audit(path):
    path = Path(path)
    raw = path.read_bytes()
    result = json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)
    source = Path('artifacts/results/workload/provisioning_holdout/inputs')
    for name,value in result['source_sha256'].items():
        if sha256((source/name).read_bytes()).hexdigest()!=value:
            raise ValueError('Training input changed')
    if (result['provenance']['git_status'] or result['registration_sha256'] !=
            sha256(Path('docs/methods/COHORT_PLACEMENT_PROBE.md').read_bytes()).hexdigest()):
        raise ValueError('Source or registration mismatch')
    if (result['layer'], result['window'], result['rx_depth'], result['training_requests'],
            result['rounds'], result['candidates_per_round'],result['seed']) != ('0',192,3,64,8,256,8109):
        raise ValueError('Probe configuration mismatch')
    requests=json.loads(gzip.decompress((source/'training_routes.json.gz').read_bytes()))
    x,w=cohort_matrix(requests,0,128)
    if len(x)!=result['training_windows'] or len(x)!=10752:
        raise ValueError('Training coverage mismatch')
    designs=candidate_designs()[0]
    designs={k:designs[k] for k in ('home','k2','wide')}
    designs['c']=target_design(192)[0]
    baseline={'modulo':[e%36 for e in range(128)],
        'marginal_lpt':json.loads((source/'owners.json').read_text())['0']['compute_by_expert']}
    final=dict(baseline)
    matrices={k:resource_matrix(d,192,3) for k,d in designs.items()}
    accepted=0
    if set(result['searches'])!=set(designs):
        raise ValueError('Missing fabric')
    for label, search in result['searches'].items():
        matrix=matrices[label]
        initial=min(baseline,key=lambda k:score(x,w,baseline[k],matrix))
        if initial!=search['initial'] or len(search['history'])!=8:
            raise ValueError('Wrong training-selected baseline or round count')
        owners=baseline[initial].copy()
        counts=np.bincount(owners,minlength=36)
        for index, step in enumerate(search['history']):
            before=score(x,w,owners,matrix)
            if step['round']!=index or abs(before-step['before'])>1e-10:
                raise ValueError('Incorrect before score')
            if step['swap'] is not None:
                a,b=step['swap']
                if not 0<=a<b<128 or owners[a]==owners[b]:
                    raise ValueError('Illegal exchange')
                owners[a],owners[b]=owners[b],owners[a]
                accepted+=1
            after=score(x,w,owners,matrix)
            if abs(after-step['after'])>1e-10 or after>before+1e-10:
                raise ValueError('Incorrect or worsening exchange')
        if (owners!=search['owners'] or abs(score(x,w,owners,matrix)-search['score'])>1e-10
                or not np.array_equal(np.bincount(owners,minlength=36),counts)):
            raise ValueError('Final mapping or capacity differs')
        final[label+'_cohort']=owners
    if set(final)!=set(result['scores']):
        raise ValueError('Cross-evaluation coverage mismatch')
    for name, owners in final.items():
        for label,matrix in matrices.items():
            value=score(x,w,owners,matrix)
            if abs(value-result['scores'][name][label])>1e-10:
                raise ValueError('Cross-evaluation score mismatch')
            # An independent closed form checks the uniform reciprocal designs.
            if label in ('home','wide','c'):
                loads=np.column_stack([x[:,np.asarray(owners)==c].sum(axis=1) for c in range(36)])
                if label=='home':
                    peaks=loads.max(axis=1)
                else:
                    fractions=np.array(designs[label].layout.shares)
                    memory=fractions.reshape(36,36,32).sum(axis=2)
                    peaks=(loads@memory).max(axis=1)
                expected=float(peaks@w/w.sum())
                if not np.isclose(value,expected,rtol=0,atol=1e-10):
                    raise ValueError('Resource matrix disagrees with independent memory-work formula')
    return dict(verified=True,provenance=provenance(),source_commit=result['provenance']['commit'],
        raw_sha256=sha256(raw).hexdigest(),training_windows=10752,accepted_swaps=accepted,
        reconstructed_cross_scores=24,unchanged_resident_counts=True,
        scope='Training objective and swap reconstruction, no new finite-task execution or test-set use')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True)
    p.add_argument('--output',required=True)
    args=p.parse_args()
    result=audit(args.source)
    Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
