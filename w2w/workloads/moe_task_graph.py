"""Compile retained real token routes into one explicitly tiled routed MoE layer.

FP8 weight blocks and FP32 scales follow the existing registered Qwen3 model
card. This is a timing/data-movement graph, not numerical inference. Each
128-wide intermediate tile performs up/gate, SiLU/product and down projection,
then passes the activation and FP32 running sum to the next tile. Expert tokens
in the same cohort reuse each weight tile. There is no cross-cohort cache.
"""
from collections import Counter, defaultdict
from dataclasses import asdict
from hashlib import sha256
import json
from math import ceil

from w2w.domain.execution import ComputeTask, DataEdge, ExecutionGraph, ReadAccess, ResidentObject
from w2w.machine.presets import machine  # historical import compatibility
from w2w.workloads.routing_input import INPUTS, LAYER_COHORTS, load_layer_routing


def residency_shards(owner, policy):
    """Geometry-only placement, independent of which experts a token selects."""
    if not 0 <= owner < 36 or policy not in ('home', 'pair', 'four_way'):
        raise ValueError('Expected a 6x6 owner and home/pair/four_way residency')
    if policy == 'home':
        return (('home', owner),)
    shards = (('home', owner), ('peer', owner ^ 1))
    if policy == 'four_way':
        vertical = owner + (6 if (owner//6) % 2 == 0 else -6)
        shards += (('vertical', vertical), ('diagonal', vertical ^ 1))
    return shards


def compile_layer(inputs=INPUTS, *, cohort='c0_b1', residency='pair'):
    """Compatibility recipe; new callers select routing explicitly."""
    return compile_routed_layer(load_layer_routing(inputs, cohort=cohort), residency=residency)


def compile_routed_layer(routing, *, residency='pair', compute_service=None):
    """Compile supplied routing, owners and residency; no file selection or I/O."""
    cohort, owners, tokens = routing.cohort, routing.owners, routing.tokens
    h, intermediate, width, experts, topk = 4096, 1536, 128, 128, 8
    tile_weight = 3*h*width + 3*(h//128)*4
    weight_bytes = tile_weight*(intermediate//width)
    if weight_bytes != routing.weight_bytes or len(owners) != experts:
        raise ValueError('Registered Qwen3 expert-weight identity differs')
    by_expert = defaultdict(list)
    for n, token in enumerate(tokens):
        if len(token['experts']) != topk or len(set(token['experts'])) != topk:
            raise ValueError('Token route is not an eight-distinct-expert selection')
        for expert in token['experts']:
            by_expert[expert].append(n)
    # Freeze all 128 experts, not just those observed in this execution.
    # The same all-expert layout is used for every cohort.
    offsets, objects = Counter(), []
    for e, owner in enumerate(owners):
        shards = residency_shards(owner, residency)
        for role, memory in shards:
            key = f'expert{e}/{role}'
            objects.append(ResidentObject(key, f'm{memory}', offsets[memory], weight_bytes//len(shards)))
            offsets[memory] += weight_bytes//len(shards)
    tasks, edges = [], []
    descriptions = {}
    for n, token in enumerate(tokens):
        tasks.extend((ComputeTask(f'token{n}/input', token['source'], 0),
                      ComputeTask(f'token{n}/combine', token['source'], ceil(2*topk*h/(256 if compute_service is None else compute_service.vector_ops_per_cycle)))))
        descriptions[f'token{n}/input'] = dict(stage='input_activation_already_resident', token=n)
        descriptions[f'token{n}/combine'] = dict(stage='weighted_combine', token=n, vector_ops=2*topk*h)
    for expert, members in sorted(by_expert.items()):
        owner, n = f'c{owners[expert]}', len(members)
        for block in range(intermediate//width):
            key = f'expert{expert}/tile{block:02}'
            reads = []
            # Retain 64 KiB interleaving and count the final partial descriptors.
            shards = residency_shards(owners[expert], residency)
            share = tile_weight//len(shards)
            for start in range(0, share, 65536):
                for role, _ in shards:
                    reads.append(ReadAccess(f'expert{expert}/{role}', block*share+start,
                                            min(65536, share-start)))
            macs = 3*n*h*width
            vector_ops = n*(9*width+2*h)
            cycles = (ceil(macs/4096)+ceil(vector_ops/256) if compute_service is None else
                      compute_service.cycles(macs,vector_ops,tile_weight))
            tasks.append(ComputeTask(key, owner, cycles, tuple(reads), scratch_bytes=4*n*width))
            descriptions[key] = dict(stage='expert_up_gate_silu_down_accumulate', expert=expert,
                                     intermediate_tile=block, tokens=members, macs=macs,
                                     vector_ops=vector_ops, weight_bytes=tile_weight)
            if block:
                edges.append(DataEdge(key+'/state', f'expert{expert}/tile{block-1:02}', key, n*h*6))
        for token in members:
            edges.append(DataEdge(f'dispatch/token{token}/expert{expert}',
                                  f'token{token}/input', f'expert{expert}/tile00', h*2))
            edges.append(DataEdge(f'combine/expert{expert}/token{token}',
                                  f'expert{expert}/tile{intermediate//width-1:02}',
                                  f'token{token}/combine', h*2))
    graph = ExecutionGraph(tuple(tasks), tuple(objects), tuple(edges))
    metadata = dict(schema='w2w.moe-layer-input.v1', scope='one_routed_ffn_layer_timing',
        model=routing.model, model_source=routing.model_source, cohort=cohort,
        tokens=tokens, owner_policy='existing frozen training marginal LPT; no retuning',
        owners=owners, residency_policy=residency,
        residency=('100% home, fixed owner' if residency == 'home' else
                   '50% home + 50% owner XOR 1, fixed for every intermediate tile' if residency == 'pair'
                   else '25% per memory in fixed aligned 2x2 group containing owner; home/peer/vertical/diagonal'),
        layout_sha256=sha256(json.dumps([asdict(o) for o in objects], sort_keys=True).encode()).hexdigest(),
        precision=dict(weights='FP8', scales='FP32 per 128x128 block', activation='BF16', accumulator='FP32'),
        shape=dict(hidden=h, intermediate=intermediate, intermediate_tile=width, experts=experts, topk=topk),
        compute_model=dict(macs_per_cycle=4096, vector_ops_per_cycle=256, period_ps=1000,
                           calibrated=False, policy='blocking tile; no inter-tile prefetch'),
        native_word_bytes=32, read_descriptor_bytes=4096,
        weight_read_bytes=sum(r.size_bytes for t in graph.tasks for r in t.reads),
        dispatch_bytes=len(tokens)*topk*h*2, combine_bytes=len(tokens)*topk*h*2,
        task_semantics=descriptions,
        omitted=['attention', 'routing projection (selections supplied)', 'KV', 'whole-model serving', 'numerical values'],
        source_hashes=routing.source_hashes)
    if compute_service is not None:metadata['compute_model']=compute_service.record()
    return graph, metadata
