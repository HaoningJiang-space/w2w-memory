"""Import one-layer expert selections into an explicitly cold weight-read DAG.

Routing capture is input evidence. This module neither captures a model nor
infers activity from top-k. Reuse is once per expert within each batch only.
"""
from collections import Counter

from w2w.workloads.read_trace import ReadObject, ReadSpan, ReadTask, ReadTrace, digest, integer


def validate_capture(capture):
    required = {'schema', 'evidence', 'source', 'split', 'layer', 'experts', 'batches'}
    if set(capture) != required or capture['schema'] != 'w2w.moe-routes.v1':
        raise ValueError('Expected the exact w2w.moe-routes.v1 capture fields')
    if (capture['evidence'] not in ('synthetic', 'captured') or not capture['source']
            or not isinstance(capture['layer'], str) or not capture['layer']
            or capture['split'] not in ('train', 'test')):
        raise ValueError('Capture evidence, source, layer and split must be explicit')
    experts = {}
    for expert in capture['experts']:
        if set(expert) != {'id', 'size_bytes'} or not isinstance(expert['id'], str) or not expert['id']:
            raise ValueError('Expert needs id and size_bytes')
        integer(expert['size_bytes'], 'expert size', 32)
        if expert['size_bytes'] % 32 or expert['id'] in experts:
            raise ValueError('Expert IDs must be unique and byte sizes 32-byte aligned')
        experts[expert['id']] = expert['size_bytes']
    if not experts or not capture['batches']:
        raise ValueError('Nonempty experts and batches required')
    ids = set()
    for batch in capture['batches']:
        if (set(batch) != {'id', 'selections'} or not isinstance(batch['id'], str)
                or not batch['id'] or batch['id'] in ids or not batch['selections']):
            raise ValueError('Unique batch IDs and token expert selections required')
        ids.add(batch['id'])
        for token in batch['selections']:
            if not token or len(set(token)) != len(token) or any(e not in experts for e in token):
                raise ValueError('Each token must select known, distinct experts')
    return experts


def compile_moe_reads(training, evaluation, compute_count=36):
    """One training-only LPT expert assignment, shared by every architecture.

    This provides a reasonable private baseline without a test-activity oracle.
    Geometry-specific data striping is compiled independently afterward.
    """
    integer(compute_count, 'compute_count', 1)
    sizes = validate_capture(training)
    if validate_capture(evaluation) != sizes or training['layer'] != evaluation['layer']:
        raise ValueError('Training and evaluation must use identical expert objects and layer')
    if training['split'] != 'train' or evaluation['split'] != 'test':
        raise ValueError('Training-only assignment requires train and test captures')
    if {b['id'] for b in training['batches']} & {b['id'] for b in evaluation['batches']}:
        raise ValueError('Train/test batch IDs overlap')
    demand = Counter()
    for batch in training['batches']:
        for expert in {e for token in batch['selections'] for e in token}:
            demand[expert] += sizes[expert]
    assigned = {}
    loads = [0] * compute_count
    resident = [0] * compute_count
    for expert in sorted(sizes, key=lambda e: (-demand[e], -sizes[e], e)):
        c = min(range(compute_count), key=lambda c: (loads[c], resident[c], c))
        assigned[expert] = c
        loads[c] += demand[expert]
        resident[c] += sizes[expert]
    objects = tuple(ReadObject(e, sizes[e], assigned[e]) for e in sorted(sizes))
    tasks = []
    previous = ()
    for index, batch in enumerate(evaluation['batches']):
        expert_tasks = []
        for expert in sorted({e for token in batch['selections'] for e in token}):
            # Numeric index avoids collisions with arbitrary captured IDs.
            key = f'batch{index}/expert{sorted(sizes).index(expert)}'
            tasks.append(ReadTask(key, assigned[expert], (ReadSpan(expert, 0, sizes[expert]),), previous))
            expert_tasks.append(key)
        barrier = f'batch{index}/join'
        tasks.append(ReadTask(barrier, None, dependencies=tuple(expert_tasks)))
        previous = (barrier,)
    train_hash, eval_hash = digest(training), digest(evaluation)
    trace = ReadTrace(objects, tuple(tasks), evaluation['evidence'],
                      f'{evaluation["source"]}; route_sha256={eval_hash}; training_sha256={train_hash}')
    return trace, dict(schema='w2w.moe-read-import.v1', training_sha256=train_hash,
                       evaluation_sha256=eval_hash, layer=evaluation['layer'],
                       assignment=assigned, training_read_bytes_per_compute=loads,
                       resident_bytes_per_compute=resident,
                       policy='LPT by training cold-read bytes, then resident bytes; same assignment in all designs',
                       semantics='One cold full expert-weight read per selected expert per batch; '
                                 'intra-batch reuse, no cross-batch cache; sequential batch joins; '
                                 'no expert GEMM, dispatch, combine or whole-model timing',
                       captured_routing=evaluation['evidence'] == 'captured',
                       task_timing_is_measured=False)


def synthetic_moe_captures():
    """Small, deterministic infrastructure fixture; never called a real trace."""
    experts = [dict(id=f'e{i:02}', size_bytes=32 * 32 * 13 * 4) for i in range(36)]
    base = dict(schema='w2w.moe-routes.v1', evidence='synthetic',
                source='w2w deterministic read-infrastructure fixture v1',
                layer='synthetic_layer', experts=experts)
    train = dict(base, split='train', batches=[dict(id='train/full',
                         selections=[[f'e{i:02}', f'e{(i+1)%36:02}'] for i in range(36)])])
    test = dict(base, split='test', batches=[
        dict(id='test/full', selections=[[f'e{i:02}'] for i in range(36)]),
        dict(id='test/sparse', selections=[[f'e{i:02}', f'e{(i+11)%36:02}'] for i in (0, 6, 14, 23)]),
        dict(id='test/single', selections=[['e00'], ['e00']])])
    return train, test
