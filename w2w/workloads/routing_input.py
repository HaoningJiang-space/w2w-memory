"""Select registered routing and owners before compiling an FFN task graph."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from w2w.common.io import read_json

INPUTS = Path('artifacts/results/workload/cohort_replay/inputs')
LAYER_COHORTS = {'c0_b1': (0, 1), 'c1_b1': (1, 1), 'c2_b4': (2, 4)}


@dataclass(frozen=True)
class LayerRouting:
    cohort: str
    tokens: list
    owners: list
    model: object
    model_source: object
    weight_bytes: int
    source_hashes: dict


def load_layer_routing(inputs=INPUTS, *, cohort='c0_b1'):
    """Keep the historical frozen cohort selection and byte identities."""
    inputs = Path(inputs)
    if cohort not in LAYER_COHORTS:
        raise ValueError('Only the predeclared layer cohorts are supported')
    routes = {r['id']: r for r in read_json(inputs/'routes.json.gz')}
    split = read_json(inputs/'summary.json')['split']
    group, batch_size = LAYER_COHORTS[cohort]
    selected = split['groups'][group][:batch_size]
    if len(selected) != batch_size:
        raise ValueError('Insufficient registered requests')
    owners = read_json(inputs/'owners.json')['marginal']
    previous = read_json(inputs/cohort/'marginal_spec.json')
    if previous['layers'][0]['compute_by_expert'] != owners:
        raise ValueError('Frozen marginal owner identity differs')
    tokens = [dict(id=key, source=f'c{i%36}', decode_step=17, layer='0',
                   experts=routes[key]['decode'][16][0], raw_source=routes[key]['source'])
              for i, key in enumerate(selected)]
    hashes = {str(p.relative_to(inputs)): sha256(p.read_bytes()).hexdigest() for p in
              (inputs/'routes.json.gz', inputs/'owners.json', inputs/'summary.json',
               inputs/cohort/'marginal_spec.json')}
    return LayerRouting(cohort, tokens, owners, previous['model'], previous['weight_source'],
                        previous['layers'][0]['weight_bytes'], hashes)
