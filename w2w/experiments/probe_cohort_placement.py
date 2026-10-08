"""Bounded training-only experiment for service-aware static expert assignment."""
import argparse
from hashlib import sha256
import gzip
import json
from pathlib import Path
import time

from w2w.provenance import provenance
from w2w.synthesis.cohort_placement import cohort_matrix, resource_matrix, score, swap_search
from w2w.synthesis.provisioning_catalog import candidate_designs
from w2w.synthesis.provisioning_target import target_design


def run(output):
    prov = provenance()
    if prov['git_status']:
        raise ValueError('Committed clean source required')
    source = Path('artifacts/results/workload/provisioning_holdout/inputs')
    requests = json.loads(gzip.decompress((source/'training_routes.json.gz').read_bytes()))
    frozen = json.loads((source/'owners.json').read_text())
    designs = candidate_designs()[0]
    designs = {k:designs[k] for k in ('home','k2','wide')}
    designs['c'] = target_design(192)[0]
    activation, weights = cohort_matrix(requests, 0, 128)
    coefficients = {k:resource_matrix(d, 192, 3) for k,d in designs.items()}
    owners = {'modulo':[e%36 for e in range(128)], 'marginal_lpt':frozen['0']['compute_by_expert']}
    result = dict(schema='w2w.cohort-placement-probe.v1',provenance=prov,layer='0',training_requests=64,
        training_windows=len(activation),batch_weights='Equal batch1/4/16 means; complete 128 decode steps',
        source_sha256={f:sha256((source/f).read_bytes()).hexdigest() for f in ('training_routes.json.gz','owners.json')},
        registration_sha256=sha256(Path('docs/methods/COHORT_PLACEMENT_PROBE.md').read_bytes()).hexdigest(),
        window=192,rx_depth=3,rounds=8,candidates_per_round=256,seed=8109,
        scope='Training-only continuous resource score. No held-out inference or finite read replay; no global optimality')
    started = time.monotonic()
    result['searches'] = {}
    for label, matrix in coefficients.items():
        # The common initialization rule is applied independently per fabric.
        initial = min(owners, key=lambda k:score(activation,weights,owners[k],matrix))
        # Only baseline starts, never a previously optimized fabric's mapping.
        search = swap_search(activation,weights,owners[initial],matrix)
        result['searches'][label] = dict(search,initial=initial,resource_columns=matrix.shape[1])
        print(label, initial, search['history'][0]['before'], search['score'], flush=True)
    owners.update({k+'_cohort':v['owners'] for k,v in result['searches'].items()})
    result['scores'] = {k:{label:score(activation,weights,value,matrix) for label,matrix in coefficients.items()}
                        for k,value in owners.items()}
    result['elapsed_seconds'] = time.monotonic()-started
    path = Path(output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2)+'\n')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True)
    run(p.parse_args().output)
