"""Patterns Behind Chaos request JSON -> modeled decode batches -> frozen reads.

Routing is observed only when the input manifest declares captured evidence.
Batch admission, weight read reuse and static ownership are separate model inputs.
No download, model execution, residency optimization, or timing inference occurs here.
"""
from collections import Counter
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path

from w2w.workloads.read_trace import ReadObject, ReadSpan, ReadTask, ReadTrace, digest, integer


@dataclass(frozen=True)
class RequestRoutes:
    id: str
    arrival_iteration: int
    # decode[step][selected-layer-index] -> tuple of expert IDs
    decode: tuple
    source: dict


def object_id(layer, expert):
    return f'layer:{layer}/expert:{expert}'


def validate_spec(spec):
    required = {'schema', 'model', 'weight_source', 'compute_count', 'layers', 'batching'}
    if set(spec) != required or spec['schema'] != 'w2w.pbc-execution.v1':
        raise ValueError('Expected exact w2w.pbc-execution.v1 fields')
    if not spec['model'] or not spec['weight_source']:
        raise ValueError('Explicit model identity and weight-byte source required')
    integer(spec['compute_count'], 'compute_count', 1)
    if not spec['layers']:
        raise ValueError('Select at least one MoE layer')
    keys = set()
    for layer in spec['layers']:
        if set(layer) != {'key', 'expert_count', 'weight_bytes', 'top_k', 'compute_by_expert'}:
            raise ValueError('Each layer needs exact expert sizes, top-k and frozen compute mapping')
        key = layer['key']
        if not isinstance(key, str) or not key or key in keys:
            raise ValueError('Layer keys must be unique strings matching raw JSON exactly')
        keys.add(key)
        integer(layer['expert_count'], 'expert_count', 1)
        integer(layer['top_k'], 'top_k', 1)
        integer(layer['weight_bytes'], 'weight_bytes', 32)
        if layer['weight_bytes'] % 32 or layer['top_k'] > layer['expert_count']:
            raise ValueError('Weights must be 32-byte aligned; top-k cannot exceed expert count')
        owners = layer['compute_by_expert']
        if len(owners) != layer['expert_count']:
            raise ValueError('Mapping must include unobserved experts, not only selected experts')
        for owner in owners:
            integer(owner, 'expert compute')
            if owner >= spec['compute_count']:
                raise ValueError('Expert compute outside declared machine')
    batch = spec['batching']
    if set(batch) != {'policy', 'batch_size', 'max_decode_steps'} or batch['policy'] not in ('fixed_cohort', 'iteration_refill'):
        raise ValueError('Explicit fixed_cohort or iteration_refill policy required')
    integer(batch['batch_size'], 'batch_size', 1)
    if batch['max_decode_steps'] is not None:
        integer(batch['max_decode_steps'], 'max_decode_steps', 1)


def normalize_selection(value, layer, where, decode):
    if value is None:
        raise ValueError(f'{where}: selected MoE layer is null; choose explicit MoE layers')
    if not isinstance(value, list) or not value:
        raise ValueError(f'{where}: expected expert ID list or token x top-k matrix')
    rows = [value] if all(type(x) is int for x in value) else value
    if decode and len(rows) != 1:
        raise ValueError(f'{where}: decode must have exactly one token; prefill cannot be mixed in')
    for row in rows:
        if (not isinstance(row, list) or len(row) != layer['top_k'] or
                any(type(e) is not int or not 0 <= e < layer['expert_count'] for e in row) or
                len(set(row)) != len(row)):
            raise ValueError(f'{where}: unknown, repeated or invalid expert IDs/top-k')
    return tuple(tuple(row) for row in rows)


def load_requests(manifest_path, spec):
    validate_spec(spec)
    path = Path(manifest_path)
    manifest = json.loads(path.read_text())
    if set(manifest) != {'schema', 'evidence', 'source', 'revision', 'requests'} or manifest['schema'] != 'w2w.pbc-files.v1':
        raise ValueError('Expected exact w2w.pbc-files.v1 manifest')
    if manifest['evidence'] not in ('captured', 'synthetic') or not manifest['source'] or not manifest['revision']:
        raise ValueError('Explicit evidence, original source and revision required')
    if not manifest['requests']:
        raise ValueError('No request files')
    ids, paths, requests = set(), set(), []
    for record in manifest['requests']:
        if set(record) != {'id', 'path', 'sha256', 'arrival_iteration'}:
            raise ValueError('Request needs id, path, sha256, arrival_iteration')
        if not isinstance(record['id'], str) or not record['id'] or record['id'] in ids:
            raise ValueError('Request IDs must be unique')
        integer(record['arrival_iteration'], 'arrival_iteration')
        file = (path.parent / record['path']).resolve()
        if file in paths:
            raise ValueError('Same request file cannot be replayed as two distinct requests')
        ids.add(record['id']); paths.add(file)
        raw = file.read_bytes()
        if sha256(raw).hexdigest() != record['sha256']:
            raise ValueError(f'{record["id"]}: raw file SHA256 mismatch')
        tokens = json.loads(raw)
        if not isinstance(tokens, list) or len(tokens) < 2:
            raise ValueError('Expected prefill record followed by at least one decode token')
        decode, prefill_count = [], None
        for step, token in enumerate(tokens):
            if not isinstance(token, dict):
                raise ValueError('Output token must map exact layer keys to selections')
            selections, counts = [], []
            for layer in spec['layers']:
                if layer['key'] not in token:
                    raise ValueError(f'Missing selected layer {layer["key"]!r}')
                rows = normalize_selection(token[layer['key']], layer,
                                           f'{record["id"]}/token{step}/{layer["key"]}', step > 0)
                selections.append(rows[0]); counts.append(len(rows))
            if step == 0:
                if len(set(counts)) != 1:
                    raise ValueError('Prefill input-token counts differ across selected layers')
                prefill_count = counts[0]
            else:
                decode.append(tuple(selections))
        limit = spec['batching']['max_decode_steps']
        retained = decode if limit is None else decode[:limit]
        source = dict(record, prefill_tokens=prefill_count, raw_decode_steps=len(decode),
                      retained_decode_steps=len(retained), omitted_decode_steps=len(decode)-len(retained))
        requests.append(RequestRoutes(record['id'], record['arrival_iteration'], tuple(retained), source))
    return tuple(requests), manifest


def batches(requests, policy, size):
    """Logical iteration schedule, NOT wall-clock arrivals or measured batching.

    A refill is admitted only at an iteration boundary. Each resident request
    contributes one next decode token. Finished requests are never padded/reused.
    """
    pending = sorted(enumerate(requests), key=lambda pair: (pair[1].arrival_iteration, pair[0]))
    pending = [request for _, request in pending]
    active = []
    iteration = 0
    while pending or active:
        if not active and pending:
            iteration = max(iteration, pending[0].arrival_iteration)
        may_admit = policy == 'iteration_refill' or not active
        if may_admit:
            while pending and len(active) < size and pending[0].arrival_iteration <= iteration:
                active.append((pending.pop(0), 0))
        if not active:
            continue
        yield iteration, tuple(active)
        active = [(request, step+1) for request, step in active if step+1 < len(request.decode)]
        iteration += 1


def compile_patterns(manifest_path, spec):
    requests, manifest = load_requests(manifest_path, spec)
    return _compile_loaded(requests, manifest, spec)


def compile_patterns_window(manifest_path, spec, decode_step):
    """One cold decode window at an explicit original step, without rewriting raw JSON.

    This does not execute preceding steps or imply their weights remain cached.
    All selected raw layers/steps are validated before selecting the window.
    """
    integer(decode_step, 'decode_step', 1)
    if spec['batching']['policy'] != 'fixed_cohort' or spec['batching']['max_decode_steps'] is not None:
        raise ValueError('Window selection requires fixed_cohort and no decode truncation')
    requests, manifest = load_requests(manifest_path, spec)
    if len(requests) != spec['batching']['batch_size'] or any(r.arrival_iteration for r in requests):
        raise ValueError('Window must contain exactly one complete cohort arriving at iteration zero')
    if any(len(r.decode) < decode_step for r in requests):
        raise ValueError('Selected decode step absent; no padding or request replacement')
    selected = tuple(replace(r, decode=(r.decode[decode_step-1],), source=dict(
        r.source, retained_decode_steps=1, omitted_decode_steps=len(r.decode)-1,
        selected_decode_steps=[decode_step])) for r in requests)
    return _compile_loaded(selected, manifest, spec, decode_step)


def _compile_loaded(requests, manifest, spec, selected_step=None):
    objects = tuple(ReadObject(object_id(layer['key'], e), layer['weight_bytes'], owner)
                    for layer in spec['layers'] for e, owner in enumerate(layer['compute_by_expert']))
    tasks, windows, previous = [], [], ()
    batch = spec['batching']
    for batch_index, (iteration, active) in enumerate(batches(requests, batch['policy'], batch['batch_size'])):
        for layer_index, layer in enumerate(spec['layers']):
            selected = [request.decode[step][layer_index] for request, step in active]
            counts = Counter(e for token in selected for e in token)
            byte_demand = [0] * spec['compute_count']
            task_ids = []
            for expert in sorted(counts):
                key = f'batch{batch_index}/layer{layer_index}/expert{expert}'
                owner = layer['compute_by_expert'][expert]
                amount = layer['weight_bytes']
                tasks.append(ReadTask(key, owner,
                                      (ReadSpan(object_id(layer['key'], expert), 0, amount),), previous))
                task_ids.append(key); byte_demand[owner] += amount
            barrier = f'batch{batch_index}/layer{layer_index}/join'
            tasks.append(ReadTask(barrier, None, dependencies=tuple(task_ids)))
            previous = (barrier,)
            windows.append(dict(id=f'batch{batch_index}/layer{layer_index}', iteration=iteration,
                layer=layer['key'], request_tokens=[dict(id=r.id, decode_step=selected_step or s+1) for r,s in active],
                token_count=len(active), expert_token_counts=dict(sorted(counts.items())),
                activated_experts=sorted(counts), task_ids=task_ids, join_task=barrier,
                read_bytes_per_compute=byte_demand, logical_read_bytes=sum(byte_demand),
                no_reuse_reference_bytes=sum(counts.values())*layer['weight_bytes']))
    trace = ReadTrace(objects, tuple(tasks), manifest['evidence'],
                      f'{manifest["source"]}@{manifest["revision"]}; '
                      f'manifest_sha256={digest(manifest)}; execution_spec_sha256={digest(spec)}'
                      + (f'; cold_selected_decode_step={selected_step}' if selected_step is not None else ''))
    summary = dict(schema='w2w.pbc-demand.v1', trace_sha256=trace.sha256,
        manifest_sha256=digest(manifest), execution_spec_sha256=digest(spec),
        evidence=manifest['evidence'], captured_routing=manifest['evidence']=='captured',
        model=spec['model'], source=manifest['source'], revision=manifest['revision'],
        requests=[r.source for r in requests], windows=windows,
        total_logical_read_bytes=sum(w['logical_read_bytes'] for w in windows),
        total_resident_weight_bytes=sum(o.size_bytes for o in objects),
        semantics=dict(stage='decode_only; prefill validated but never charged to decode',
            reuse='One full routed-expert weight read per layer/batch; intra-batch reuse; cold across batches',
            batching='Logical decode iterations, not measured wall-clock arrivals or serving throughput',
            placement='Caller-supplied compute_by_expert frozen for all architectures; no trace-fitted assignment',
            timing='Selected layers/batches execute sequentially with joins; GEMM/dispatch/combine/KV/dense/shared experts omitted',
            weight_bytes='Explicit supplied bytes, including chosen precision/metadata; not inferred from token counts',
            scope='Selected routed MoE layers only, not full-model capacity or end-to-end latency'))
    if selected_step is not None:
        summary['window_selection'] = dict(original_decode_step=selected_step,
            preceding_steps_executed=False, cache_state='cold by explicit model assumption')
    return trace, summary


def project_demand(design, trace, windows):
    """Static byte accounting via the existing exact address residency compiler."""
    from w2w.workloads.read_residency import ReadResidency
    from w2w.service.read_replay import design_record
    residence = ReadResidency(design, trace)
    by_id = {task.id: task for task in trace.tasks}
    nm = len(design.geometry.memory_xy)
    banks_per_memory = len(residence.bank_words)//nm
    out = []
    for window in windows:
        bank = Counter()
        for task_id in window['task_ids']:
            bank.update(residence.task_bytes(by_id[task_id]))
        memory = [0]*nm
        for b, amount in bank.items(): memory[b//banks_per_memory] += amount
        assert sum(memory) == window['logical_read_bytes']
        out.append(dict(id=window['id'], bank_bytes=dict(sorted(bank.items())), memory_bytes=memory))
    return dict(design_sha256=digest(design_record(design)), residence_sha256=residence.sha256,
                resident_bytes_per_bank=[n*trace.word_bytes for n in residence.bank_words], windows=out)
