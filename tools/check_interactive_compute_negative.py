#!/usr/bin/env python3
"""Read-only negative checks on an already accepted native compact result."""
import argparse
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from tools.run_interactive_compute_gate import analyze
from w2w.validation.interactive_compute import audit_interactive_compute, expand_interactive_compute
from w2w.validation.vertical_access import audit_vertical_result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gate',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Preserve existing supplemental receipt')
    analyze(args.gate)
    started=json.loads((args.gate/'STARTED.json').read_text())
    frozen=args.gate/'source'
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=frozen,text=True).strip()!=started['source_commit']:
        raise ValueError('Frozen execution checkout identity changed')
    if subprocess.check_output(['git','status','--porcelain'],cwd=frozen):
        raise ValueError('Frozen checkout contains changed or untracked source')
    path=args.gate/'run-stable-0-compact/result.json.gz'
    with gzip.open(path,'rt') as stream:raw=json.load(stream)
    audit_interactive_compute(raw);audit_vertical_result(expand_interactive_compute(raw))
    def first_marker(r):return next(e for e in r['events'] if e['kind']=='interactive_compute_epoch')
    def delay_first_ready(r):
        # Avoid rejection merely because moving a same-time event invalidates
        # compact insertion anchors: challenge the causal frontier itself.
        expanded=expand_interactive_compute(r);r.clear();r.update(expanded)
        r['interactive_compute']['evidence']='full'
        event=next(e for e in r['events'] if e['kind']=='stream_operand_ready' and e['object_offset']==0)
        event['time_ps']=r['drained_ps']-1;r['events'].sort(key=lambda e:e['time_ps'])
    mutations={
        'wrong_original_frontier':lambda r:r['interactive_compute']['intervals'][0].update(committed_prefix_bytes=65536),
        'wrong_consumed_before':lambda r:r['interactive_compute']['intervals'][0].update(consumed_before=4),
        'wrong_batch_total':lambda r:r['interactive_compute'].update(batched_compute_cycles=1),
        'duplicate_marker':lambda r:r['events'].append(deepcopy(first_marker(r))),
        'unknown_marker_field':lambda r:first_marker(r).update(unregistered=True),
        'unknown_contract_field':lambda r:r['interactive_compute'].update(unregistered=True),
        'missing_marker':lambda r:r['events'].remove(first_marker(r)),
        'wrong_equal_time_position':lambda r:first_marker(r).update(tie_runs=[[0,999999]]),
        'malformed_equal_time_position':lambda r:first_marker(r).update(tie_runs=[[]]),
        'frontier_commit_after_service':delay_first_ready,
        'aggregate_policy_relabel':lambda r:r['operand_readiness'].update(policy='byte_count'),
    }
    checks=[]
    for name,change in mutations.items():
        bad=deepcopy(raw);change(bad)
        try:audit_interactive_compute(bad);audit_vertical_result(expand_interactive_compute(bad))
        except ValueError as exc:checks.append(dict(name=name,rejected=True,reason=str(exc)))
        else:raise ValueError('Accepted corrupted native evidence: '+name)
    receipt=dict(passed=True,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        execution_commit=started['source_commit'],frozen_checkout_clean=True,
        input_result_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        gate_manifest_sha256=hashlib.sha256((args.gate/'COMPLETE.json').read_bytes()).hexdigest(),checks=checks)
    args.output.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print('Native readback and',len(checks),'negative checks passed')


if __name__=='__main__':main()
