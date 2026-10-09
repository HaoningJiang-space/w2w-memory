"""Frozen owner assignments and ID-only evaluation requests for cohort replay."""
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path

from w2w.workloads.read_trace import digest

METHOD = Path('docs/methods/COHORT_REPLAY_STUDY.md')
OLD_INPUTS = Path('artifacts/results/workload/provisioning_holdout/inputs')
PROBE = Path('artifacts/results/workload/cohort_design/probe.json.gz')
PROBE_SHA = '0aecb504642006baca0559d834cf9b90255d7e3175abf3f86bfb0644b5cd57cc'
STRUCTURES = ('home', 'k2', 'wide', 'c')
STEPS = (17, 65, 113)
BATCHES = (1, 4, 16)


from w2w.common.io import read_json


def frozen_owners():
    if sha256(PROBE.read_bytes()).hexdigest() != PROBE_SHA:
        raise ValueError('Frozen training probe changed')
    probe = read_json(PROBE)
    baseline = read_json(OLD_INPUTS / 'owners.json')['0']['compute_by_expert']
    result = {'marginal': baseline}
    for label in STRUCTURES:
        search = probe['searches'][label]
        if search['initial'] != 'marginal_lpt' or Counter(search['owners']) != Counter(baseline):
            raise ValueError('Training initialization or resident counts changed')
        result[label] = search['owners']
    return result


def select_requests(corpus, previous, seed=8110):
    """Exclude every previous timed/training request before looking at routing."""
    split = previous['split']
    excluded = set(split['training']) | set(split['excluded_previous']) | set(sum(split['tests'], []))
    entries = corpus['requests']
    if len({r['id'] for r in entries}) != len(entries):
        raise ValueError('Duplicate corpus request')
    subjects = sorted({r['id'].split('/')[-2] for r in entries})
    groups = [[], [], []]
    for subject in subjects:
        available = [r['id'] for r in entries if r['id'].split('/')[-2] == subject and r['id'] not in excluded]
        available.sort(key=lambda key: sha256(f'{seed}:{key}'.encode()).hexdigest())
        if len(available) < 6:
            raise ValueError('Insufficient fresh requests')
        for group in range(3):
            groups[group].extend(available[2*group:2*group+2])
    for group in groups:
        group.sort(key=lambda key: sha256(f'{seed}:cohort:{key}'.encode()).hexdigest())
    return dict(seed=seed, groups=groups, excluded=sorted(excluded))


def cases(split):
    return [dict(id=f'c{g}_b{b}', group=g, layer='0', decode_step=STEPS[g], batch_size=b,
                 requests=group[:b]) for g, group in enumerate(split['groups']) for b in BATCHES]


def jobs():
    return [(f'c{g}_b{b}', label, mode) for g in range(3) for b in BATCHES
            for label, mode in [*( (s, m) for s in STRUCTURES for m in ('marginal', 'cohort')),
                                ('c_dup', 'cohort')]]


def owner_key(label, mode):
    return 'marginal' if mode == 'marginal' else ('c' if label == 'c_dup' else label)


def logical_signature(trace):
    """Task/data identity with only compute assignment and provenance removed."""
    record = trace.record()
    record.pop('source')
    for row in (*record['objects'], *record['tasks']):
        row.pop('compute')
    return digest(record)
