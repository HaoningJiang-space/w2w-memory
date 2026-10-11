"""Accepted mapping comparisons cannot by themselves accept a new architecture."""
from .energy_edp import threshold


def baseline_screen(cases):
    batches=(1,4,16,32);policies=('reference','phase_split','up_local')
    wanted={(b,p) for b in batches for p in policies};by={}
    for case in cases:
        key=(case['B'],case['baseline'])
        if key not in wanted or key in by or case.get('passed') is not True or case.get('full_captured_lifecycle') is not True:
            raise ValueError('Unique completed full-lifecycle baseline cases required')
        by[key]=case
    if set(by)!=wanted:raise ValueError('Every registered B/mapping case must finish')
    rows={}
    for B in batches:
        reference=by[B,'reference']
        identity=('registration_sha256','cohort_sha256','original_request_hashes','executed_layers',
            'token_expert_assignments','npu_macs','npu_service_cycles','npu_service')
        for policy in policies:
            if any(by[B,policy][k]!=reference[k] for k in identity):raise ValueError('Comparisons changed trace identity or logical/kernel work')
        metrics={p:dict(completion_ps=by[B,p]['proof']['makespan_ps'],late_window_ps=by[B,p]['late_window_time_ps'],
            native_bytes=by[B,p]['proof']['native_bytes'],noc_cell_bit_mm=by[B,p]['activity_counts']['noc_cell_bit_mm']) for p in policies}
        pareto=[p for p in policies if not any(all(metrics[q][k]<=v for k,v in metrics[p].items())
            and any(metrics[q][k]<v for k,v in metrics[p].items()) for q in policies if q!=p)]
        fastest=min(policies,key=lambda p:(metrics[p]['completion_ps'],metrics[p]['late_window_ps'],p))
        record=lambda p:dict(makespan_ps=by[B,p]['proof']['makespan_ps'],drained_ps=by[B,p]['proof']['drained_ps'],counts=by[B,p]['activity_counts'])
        rows[str(B)]=dict(metrics=metrics,fastest_observed_mapping=fastest,non_dominated_mappings=pareto,
            speedup_over_reference={p:metrics['reference']['completion_ps']/metrics[p]['completion_ps'] for p in policies},
            covered_activity_edp={p:threshold(record('reference'),record(p)) for p in policies if p!='reference'})
    return dict(passed=True,complete_mapping_screen=True,batches=rows,
        architecture_gate_passed=False,new_hardware_justified=False,
        hardware_gate=dict(status='unproven',reason='All compared runs use unchanged physical hardware; no costed structural candidate or strongest-software-baseline comparison has been accepted.',
            required=['Completed audited structural intervention on the real workload','Comparison against the strongest legal mapping and kernel dataflow',
                'Explicit physical resource, wire, buffering and area/energy cost bounds']),
        scope='Complete mapping evidence ranks observed latency/activity tradeoffs, not calibrated total energy or area. A successful baseline screen is distinct from G5 architecture acceptance; lack of evidence is not proof that a new structure has no value.')
