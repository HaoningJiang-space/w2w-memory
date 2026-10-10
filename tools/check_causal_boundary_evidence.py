#!/usr/bin/env python3
"""Independent saved census accounting and explicit negative research verdict."""
import argparse,gzip,hashlib,json,subprocess,sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO))
from tools.run_causal_boundary_gate import analyze
from tools.check_simulator_equivalence import canonical


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def result(path):
    with gzip.open(path,'rt') as file:return json.load(file)


def checked_census(path):
    summary=read(path/'CENSUS.json');physical=result(path/'result.json.gz')
    for name,key in [('input.json','input_sha256'),('result.json.gz','result_sha256'),('wakeups.json.gz','wakeups_sha256')]:
        if sha(path/name)!=summary[key]:raise ValueError('Changed census '+name)
    rows=result(path/'wakeups.json.gz');calls=Counter();events=Counter();classes=Counter();blockers=Counter()
    for row in rows:
        calls.update(row['calls']);events.update(row['events']);blockers.update(row['gap_blockers'])
        c,v=row['calls'],row['events']
        external=sum(n for k,n in v.items() if k not in ('stream_compute','compute_service'))
        external+=sum(c.get(k,0) for k in ('network_inject','network_receive','network_completed','array_callbacks','gateway_ready_atoms'))
        quiet=not external and not row['resource_projection_changed']
        compute=bool(v.get('stream_compute') or v.get('compute_service'))
        classes.update(dict(with_observed_interface_progress=bool(external),
            resource_projection_changes=row['resource_projection_changed'],
            no_observed_interface_or_resource_change=quiet,quiet_with_compute_service=quiet and compute,
            quiet_without_compute_service=quiet and not compute,potential_active_array_gap=not row['gap_blockers'],
            with_array_callback=bool(c.get('array_callbacks')),with_gateway_ready=bool(c.get('gateway_ready_atoms')),
            with_network_progress=bool(c.get('network_inject') or c.get('network_receive') or c.get('network_completed')),
            empty_advance_reply=bool(c.get('network_api_advance') and not (
                c.get('network_inject') or c.get('network_receive') or c.get('network_completed')))))
    if (dict(calls)!=summary['calls'] or dict(events)!=summary['appended_events']
            or dict(classes)!=summary['classification'] or dict(blockers)!=summary['gap_blockers']):
        raise ValueError('Census summary differs from wakeup capture')
    times=[r['time_ps'] for r in rows]
    periods={physical['spec']['noc_period_ps'],physical['spec']['dram_period_ps'],
             *(t['compute_period_ps'] for t in physical['spec']['tiles'])}
    clock={t for p in periods for t in range(0,physical['drained_ps']+1,p)}
    if (times!=sorted(set(times)) or len(rows)!=physical['kernel_iterations']
            or len(rows)!=summary['kernel_iterations'] or len(clock)!=summary['clock_union']
            or len(set(times)-clock)!=summary['off_clock_wakeups']):
        raise ValueError('Census clock identity differs')
    native=physical['native']
    if (calls['array_callbacks']!=native['completed_atoms'] or calls['gateway_ready_atoms']!=native['completed_atoms']
            or calls['atom_admission_accepted']!=native['accepted_atoms']
            or calls['atom_admission_attempt']-calls['atom_admission_accepted']!=native['rejected_attempts']):
        raise ValueError('Census native atom accounting differs')
    return summary,physical


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path)
    p.add_argument('output',type=Path);a=p.parse_args()
    if a.output.exists():raise ValueError('Keep existing receipt immutable')
    analyze(a.root/'gate-001')
    manifest=read(a.root/'census-002/COMPLETE.json')
    for name,expected in manifest['artifacts'].items():
        if sha(a.root/'census-002'/name)!=expected:raise ValueError('Changed diagnostic artifact')
    rows=[]
    for case in ('stable','transport','concurrent'):
        summary,physical=checked_census(a.root/'census-002'/case)
        baseline=result(a.root/f'gate-001/run-{case}-0-off/result.json.gz')
        if canonical(physical)!=canonical(baseline):raise ValueError('Census changes physical execution '+case)
        old_checks=[]
        if case in ('stable','transport'):
            old=Path('/Projects/haoning/w2w-full-system-interactive-epoch-20261010/gate-001')/f'run-{case}-0-off'
            original=result(old/'result.json.gz');left,right=canonical(original),canonical(baseline)
            left['native'].pop('bridge_sha256');right['native'].pop('bridge_sha256')
            if left!=right:raise ValueError('Ordinary bridge behavior differs from accepted source '+case)
            for key in ('endpoint_trace_sha256','endpoint_trace_counts','commands_sha256','input_sha256'):
                if read(old/'worker.json')[key]!=read(a.root/f'gate-001/run-{case}-0-off/worker.json')[key]:
                    raise ValueError('Accepted ordinary fingerprint differs '+key)
            old_checks.append('old accepted result, command and endpoint fingerprints equal; only bridge identity changed')
        n=summary['kernel_iterations'];inter=summary['classification']['with_observed_interface_progress']
        rows.append(dict(case=case,clock_wakeups=n,observed_interface_times=inter,
            descriptive_clock_per_observed_interaction=n/inter,classification=summary['classification'],
            source_bridge_equivalence=old_checks,diagnostic_changes_physical_record=False,
            census_sha256=sha(a.root/'census-002'/case/'CENSUS.json')))
    gate=read(a.root/'gate-001/VERIFIED.json')
    active=any(r['coordination_audit']['intervals'] for r in gate['cases'])
    # Audit success is deliberately separate from the research success gate.
    receipt=dict(evidence_verified=True,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        execution_commit=read(a.root/'gate-001/STARTED.json')['source_commit'],census=rows,
        active_coordination_demonstrated=active,wakeup_target_40_percent_achieved=any(
            r['iterations']['coordinated']<=0.6*r['iterations']['off'] for r in gate['cases']),
        active_first_callback_intervals=sum(r['coordination_audit']['intervals'] for r in gate['cases']),
        gate_verified_sha256=sha(a.root/'gate-001/VERIFIED.json'),
        conclusion='first-callback primitive tested; no certified active system interval in these inputs; no acceleration claim',
        limits='observed interaction density is descriptive; state projection is not a sufficiency proof')
    a.output.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print('Saved evidence verified; active system compression:',active)


if __name__=='__main__':main()
