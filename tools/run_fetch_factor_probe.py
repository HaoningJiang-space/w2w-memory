#!/usr/bin/env python3
"""Fixed two-expert native probe: projection release x issue order, two fetch slots."""
import argparse
from dataclasses import asdict
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from w2w.architecture.compiler import compile_machine
from w2w.architecture.presets import vertical_memory
from w2w.backends.booksim.adapter import factory
from w2w.backends.ramulator import VerticalRWDL
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.io import write_json
from w2w.mapping.compute_placement import place_compute
from w2w.mapping.lowering import lower
from w2w.mapping.static_weights import static_weights
from w2w.provenance import revision
from w2w.system.kernel import execute_system
from w2w.validation.request_control import audit_request_control
from w2w.validation.vertical_access import audit_vertical_result
from w2w.analysis.ffn_stages import stages
from w2w.analysis.placement_pressure import summarize_pressure
from w2w.workloads.moe import build_moe


SHAPE = dict(hidden=1024, intermediate=1536, block_width=128, experts=128, topk=2)
ACTIVE = (62, 108)
CASES = {f'{dependency}-{issue}-{policy}': dict(dependency=dependency, issue=issue, placement=policy)
         for policy in ('reference', 'hybrid', 'phase-split')
         for dependency in ('d0', 'd1') for issue in ('ordered', 'round_robin')}


def inputs(case):
    settings = CASES[case]
    spec = compile_machine(vertical_memory())
    logical = build_moe((ACTIVE,), **SHAPE)
    anchor = static_weights(logical, spec.stack, 'reference')
    weights = static_weights(logical, spec.stack, settings['placement'])
    placement = place_compute(logical, spec.stack, anchor)
    graph, meta = lower(logical, spec, weights, placement,
                        execution_policy='s0' if settings['dependency'] == 'd0' else 's1')
    record = dict(settings=settings, graph=asdict(graph), machine=asdict(spec.stack),
                  weights=[asdict(w) for w in weights], metadata=meta,
                  fetch_contexts=2, fetch_metadata_bytes_per_cluster=136, compute_contexts=2)
    return spec, graph, meta, record


def prepare(root):
    root.mkdir(exist_ok=False); (root / 'logs').mkdir()
    cases = {}; invariant = None
    for case in CASES:
        _, graph, meta, record = inputs(case)
        fixed = dict(tasks=record['graph']['tasks'], data=record['graph']['data'], machine=record['machine'],
                     logical=meta['logical_sha256'], macs=meta['macs'], vector_ops=meta['vector_ops'],
                     compute_placement=meta['compute_placement_sha256'],
                     catalog=[(o.id, o.size_bytes, o.storage_id) for o in graph.objects],
                     fetch_contexts=2, fetch_metadata_bytes=136, compute_contexts=2)
        if invariant is not None and invariant != fixed: raise ValueError('Probe changed work or data resources')
        invariant = fixed
        cases[case] = dict(input_sha256=digest(record), graph_sha256=digest(record['graph']),
                           weight_sha256=digest(record['weights']), settings=CASES[case])
    write_json(root / 'registration.json', dict(schema='w2w.fetch-factor-probe.v1', source_commit=revision(),
        cases=cases, fixed_sha256=digest(invariant), shape=SHAPE, active_experts=ACTIVE,
        contract='All four release/issue combinations use two paid fetch slots and the same data/MAC/issue/outstanding budgets. '
                 'D0 is serial lowering with bounded fetch, not the old unbounded-fetch S0. '
                 'Experts 62/108 are a post-hoc contention pair from the archived cold input, sharing compute service groups; '
                 'this is a mechanism probe, not independent workload generalization or a new optimized placement.'))


def run_case(root, case, binary):
    reg = json.loads((root / 'registration.json').read_text())
    spec, graph, meta, record = inputs(case)
    if revision() != reg['source_commit'] or digest(record) != reg['cases'][case]['input_sha256']:
        raise ValueError('Frozen probe source/input changed')
    directory = root / 'cases' / case; directory.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    native = VerticalRWDL(spec, refresh=True, request_control=True, gateway_trace_bin_ps=100000)
    try:
        result = execute_system(spec, graph, native=native, compute_contexts=2, fetch_contexts=2,
            read_issue_policy=CASES[case]['issue'], operand_readiness='contiguous_prefix',
            activation_sram_read_bytes_per_cycle=128, time_advance='boundaries', max_ps=1000000000,
            network_factory=factory(binary=binary, directory=directory / 'network',
                                    ready_router_ids=tuple(r.id for r in spec.routers), ready_slots=16))
    finally:
        native.close()
    result['source_commit'] = revision(); result['input_sha256'] = digest(record)
    audit = audit_vertical_result(result); control = audit_request_control(result)
    if sum(e.get('macs', 0) for e in result['events'] if e['kind'] == 'stream_compute') != meta['macs']:
        raise ValueError('Probe changed arithmetic work')
    with gzip.open(directory / 'result.json.gz', 'wt', compresslevel=3) as f: json.dump(result, f)
    write_json(directory / 'completion.json', dict(complete=True, source_commit=revision(),
        input_sha256=digest(record), makespan_ps=result['makespan_ps'], wall_seconds=time.monotonic()-start,
        audit=audit, control_audit=control))
    print(json.dumps(dict(case=case, makespan_ps=result['makespan_ps'], passed=True)), flush=True)


def fetch_admission(result, stage):
    """Replay finite slot ownership; overlap is evidence, not an additive stall."""
    live = {}; changed = {}; full = []; ownership = []
    for event in result['events']:
        if event['kind'] not in ('fetch_context_acquire', 'fetch_context_release'): continue
        tile, task, now = event['tile'], event['task'], event['time_ps']
        owners = live.setdefault(tile, {})
        if len(owners) == 2 and changed[tile] < now:
            full.append(dict(tile=tile, start_ps=changed[tile], end_ps=now,
                             owners=sorted(owners)))
        if event['kind'] == 'fetch_context_acquire':
            if task in owners or len(owners) >= 2: raise ValueError('Invalid saved fetch acquisition')
            owners[task] = now
        else:
            if task not in owners: raise ValueError('Unmatched saved fetch release')
            ownership.append(dict(tile=tile, task=task, acquire_ps=owners.pop(task), release_ps=now))
        changed[tile] = now
    if any(live.values()): raise ValueError('Saved fetch ownership did not drain')
    lifetime={}
    for window in ownership:
        row=stage['tasks'][window['task']]['milestones']
        last_issue=row.get('read_issue_last',window['acquire_ps'])
        if not window['acquire_ps']<=last_issue<=window['release_ps']:
            raise ValueError('Issue/return lifetime reordered')
        window.update(eligible_ps=row['dependency_ready'],last_descriptor_issue_ps=last_issue,
            issuing_ps=last_issue-window['acquire_ps'],return_only_ps=window['release_ps']-last_issue,
            occupied_ps=window['release_ps']-window['acquire_ps'])
        lifetime[window['task']]=window
    delays = {}
    for task in result['graph']['tasks']:
        if not task['reads']: continue
        row = stage['tasks'][task['id']]; milestones = row['milestones']
        ready, allocated = milestones['dependency_ready'], milestones['allocate']
        if allocated <= ready: continue
        overlap = []
        for window in full:
            start, end = max(ready, window['start_ps']), min(allocated, window['end_ps'])
            if window['tile'] == task['tile'] and end > start:
                overlap.append(dict(start_ps=start, end_ps=end, owners=window['owners']))
        return_slot_ps=0;any_return_ps=0;all_return_ps=0;return_windows=[]
        for window in overlap:
            cuts=sorted({window['start_ps'],window['end_ps']}|{
                lifetime[k]['last_descriptor_issue_ps'] for k in window['owners']
                if window['start_ps']<lifetime[k]['last_descriptor_issue_ps']<window['end_ps']})
            for start,end in zip(cuts,cuts[1:]):
                only=[k for k in window['owners'] if lifetime[k]['last_descriptor_issue_ps']<=start]
                return_slot_ps+=(end-start)*len(only)
                any_return_ps+=(end-start)*bool(only)
                all_return_ps+=(end-start)*(len(only)==len(window['owners']))
                return_windows.append(dict(start_ps=start,end_ps=end,owners=window['owners'],return_only_owners=only))
        delays[task['id']] = dict(tile=task['tile'], dependency_ready_ps=ready,
            allocate_ps=allocated, elapsed_ps=allocated-ready,
            full_fetch_overlap_ps=sum(w['end_ps']-w['start_ps'] for w in overlap), windows=overlap,
            return_only_slot_overlap_ps=return_slot_ps,any_return_only_full_ps=any_return_ps,
            all_return_only_full_ps=all_return_ps,issue_return_windows=return_windows)
    occupied=sum(w['occupied_ps'] for w in ownership);issuing=sum(w['issuing_ps'] for w in ownership)
    return dict(ownership_intervals=ownership, admission_delays=delays,
        lifetime_summary=dict(matrices=len(ownership),occupied_ps=occupied,issuing_ps=issuing,
            return_only_ps=occupied-issuing,average_occupied_ps=occupied/len(ownership),
            average_return_only_ps=(occupied-issuing)/len(ownership),return_only_fraction=(occupied-issuing)/occupied,
            delayed_tasks=len(delays),admission_wait_sum_ps=sum(d['elapsed_ps'] for d in delays.values()),
            maximum_admission_wait_ps=max((d['elapsed_ps'] for d in delays.values()),default=0)),
        contract='Exact saved acquire/release ownership and predecessor-ready to allocation intervals. '
                 'Overlap with two occupied fetch slots demonstrates unavailable admission capacity; '
                 'Last descriptor enqueue marks the ideal issue/return boundary; iterator exhaustion may be observed later by the current controller. '
                 'Return-only overlap identifies a state-reuse opportunity, not an execution-time saving: tags, SRAM, outstanding, native service '
                 'and a finite return table remain live. Across-task sums overlap and are not additive system stalls.')


def analyze(root):
    reg = json.loads((root / 'registration.json').read_text()); cases = {}; tools = set(); work = set()
    for case in reg['cases']:
        _, _, meta, expected = inputs(case)
        if digest(expected) != reg['cases'][case]['input_sha256']: raise ValueError('Probe input changed at readback')
        directory = root / 'cases' / case; path = directory / 'result.json.gz'
        completion = json.loads((directory / 'completion.json').read_text())
        with gzip.open(path, 'rt') as f: r = json.load(f)
        if (not completion['complete'] or r['source_commit'] != reg['source_commit'] or
                r['input_sha256'] != reg['cases'][case]['input_sha256'] or
                digest(r['graph']) != reg['cases'][case]['graph_sha256'] or
                digest(r['spec']['stack']) != digest(expected['machine']) or
                r['makespan_ps'] != completion['makespan_ps']): raise ValueError('Probe execution identity changed')
        a = audit_vertical_result(r); b = audit_request_control(r)
        if a != completion['audit'] or b != completion['control_audit']: raise ValueError('Probe physical audit changed')
        if (r['fetch_execution']['contexts_per_cluster'] != 2 or
                r['fetch_execution']['read_issue_policy'] != CASES[case]['issue'] or
                r['compute_execution']['contexts_per_cluster'] != 2 or
                sum(e.get('macs', 0) for e in r['events'] if e['kind'] == 'stream_compute') != meta['macs']):
            raise ValueError('Probe fetch or arithmetic policy changed')
        pressure = summarize_pressure(r); stage = stages(r)
        tools.add((r['network']['identity']['binary_sha256'], r['native']['bridge_sha256']))
        work.add((a['native_bytes'], meta['macs'], a['tasks'], a['physical_domains']))
        cases[case] = dict(makespan_ps=r['makespan_ps'], independent_passed=True,
            raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), audit=a, control_audit=b,
            phases=stage['phases'], projection_pairs=stage['projection_pairs'],
            fetch_admission=fetch_admission(r, stage),
            latest_finishing_predecessor_chain=stage['latest_finishing_predecessor_chain'],
            gateway_bytes=r['native']['gateway_bytes'], gateway_busy_cycles=r['native']['gateway_busy_cycles'],
            native_last_tail_ps=r['native']['native_last_tail_ps'], native_totals=pressure['native_totals'],
            actual_hop_flits_by_scope=pressure['actual_hop_flits_by_scope'],
            actual_data_lane_byte_um=pressure['actual_data_lane_byte_um'])
    if len(tools) != 1 or len(work) != 1: raise ValueError('Probe copied native service or changed work/tools')
    effects = {}
    for policy in ('reference', 'hybrid', 'phase-split'):
        t = lambda dep, issue: cases[f'{dep}-{issue}-{policy}']['makespan_ps']
        effects[policy] = dict(dependency_effect_ordered_ps=t('d1','ordered')-t('d0','ordered'),
            dependency_effect_round_robin_ps=t('d1','round_robin')-t('d0','round_robin'),
            issue_effect_serial_ps=t('d0','round_robin')-t('d0','ordered'),
            issue_effect_independent_ps=t('d1','round_robin')-t('d1','ordered'),
            dependency_issue_interaction_ps=(t('d1','round_robin')-t('d0','round_robin'))-(t('d1','ordered')-t('d0','ordered')))
    return dict(schema='w2w.fetch-factor-analysis.v1', passed=True, execution_source_commit=reg['source_commit'],
                analysis_source_commit=revision(), native_tools=list(next(iter(tools))), cases=cases,
                effects=effects, contract=reg['contract'])


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', type=Path, required=True)
    action = p.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare', action='store_true'); action.add_argument('--run', action='store_true')
    action.add_argument('--case', choices=CASES); action.add_argument('--analyze', action='store_true')
    p.add_argument('--booksim-binary', type=Path, default=os.getenv('W2W_BOOKSIM_BINARY')); a = p.parse_args()
    if a.prepare: prepare(a.output)
    elif a.case: run_case(a.output, a.case, a.booksim_binary)
    elif a.run:
        reg = json.loads((a.output / 'registration.json').read_text())
        for case in reg['cases']:
            with (a.output / 'logs' / f'{case}.log').open('xb') as log:
                subprocess.run([sys.executable, __file__, '--output', str(a.output), '--case', case,
                    '--booksim-binary', str(a.booksim_binary)], stdout=log, stderr=subprocess.STDOUT, check=True)
            print(json.dumps(dict(case=case, complete=True)), flush=True)
        proof = analyze(a.output); write_json(a.output / 'analysis.json', proof)
        print(json.dumps(dict(passed=True, effects=proof['effects'])), flush=True)
    else:
        proof = analyze(a.output); write_json(a.output / 'independent-readback.json', proof)
        print(json.dumps(dict(passed=True, effects=proof['effects'])), flush=True)


if __name__ == '__main__': main()
