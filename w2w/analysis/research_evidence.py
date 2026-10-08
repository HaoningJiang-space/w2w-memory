"""Comparable evidence ledger; keeps model, mapping and physical costs separate."""
import argparse
from collections import Counter
import csv
import gzip
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOLDOUT = ROOT/'artifacts/results/workload/provisioning_holdout'


def build_ledger():
    paths = [HOLDOUT/'metrics.csv', HOLDOUT/'owner_controls.csv', HOLDOUT/'primary_audit.csv',
             ROOT/'artifacts/results/endpoint/endpoint_physical_slice.json.gz']
    metrics, owners, primary = [list(csv.DictReader(p.open())) for p in paths[:3]]
    by_owner = {r['case']: r for r in owners}
    by_primary = {(r['case'], r['label'], int(r['window'])): r for r in primary}
    evidence = []
    seen = set()
    for row in metrics:
        case, label = row['case'], row['label']
        if (case, label) in seen: raise ValueError('Duplicate metric')
        seen.add((case, label))
        same_owner = int(by_owner[case]['trained_home_slots'])
        modulo = int(by_owner[case]['modulo_home_slots'])
        # Existing controls used N128; verify Home is unchanged in paired N192
        # where registered, and retain the credit difference in the output.
        primary_home = int(by_primary[case, 'home', 128]['makespan_slots'])
        if same_owner != primary_home: raise ValueError('Owner control mismatch')
        if (case, 'home', 192) in by_primary and int(by_primary[case, 'home', 192]['makespan_slots']) != same_owner:
            raise ValueError('Home differs across request-window controls')
        time = int(row['makespan_slots'])
        evidence.append(dict(case=case, label=label, design_slots=time,
            same_owner_home_slots=same_owner, modulo_home_slots=modulo,
            speedup_same_owner_home=same_owner/time, speedup_modulo_home=modulo/time,
            posthoc_best_of_two_home_slots=min(same_owner, modulo),
            speedup_posthoc_home_diagnostic=min(same_owner, modulo)/time,
            lane_bits=int(row['export_lane_bits']), tx_rx_payload_proxy_bits=int(row['tx_plus_rx_payload_proxy_bits']),
            wire_bit_mm=float(row['access_wire_bit_mm']),
            complete_path_area_um2=None, application_speedup=None))
    physical = json.loads(gzip.decompress(paths[3].read_bytes()))
    from w2w.synthesis.provisioning_catalog import candidate_designs
    binding = Counter(candidate_designs()[0]['b_cfg'].shared_directions)
    return dict(schema='w2w.research-evidence-ledger.v1', inputs={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in paths},
        comparisons=evidence, binding_instances={str(k):v for k,v in sorted(binding.items())},
        local_physical=physical['summary'],
        rules=dict(performance='N192 held-out slot-model read stages; same-owner contrast isolates fabric',
          owner_control='Modulo/LPT Home controls used N128; lower request budget, not an advantage; paired Home N192 equality checked where present',
          posthoc='Per-window minimum of two Home layouts is an optimistic diagnostic, NOT a deployable policy or new held-out result',
          cost='Lane, payload bits and bit-mm are separate proxies; missing whole-path cell area stays null',
          physical='Old B source/RX P&R, not C/RX3; word-reservation replay and beat-reservoir RTL differ',
          pooling='Wide k3 is a fixed paired reference, not full pooling',
          mapping='Cohort owner probe has training scores only, no held-out completion result',
          native='HBM2 pilot changes native budget and is excluded from performance ranking'),
        next_decision='Static pruning controls are now archived separately; next evaluate equally trained frozen Home/k2/sharing mappings on untouched requests and check whether template reuse justifies configuration cost')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=build_ledger()
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'ledger.json').write_text(json.dumps(result,indent=2)+'\n')
    with (args.output/'comparisons.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(result['comparisons'][0]),lineterminator='\n')
        writer.writeheader();writer.writerows(result['comparisons'])
    print('RECONCILED',len(result['comparisons']),'existing rows; no new performance execution')


if __name__=='__main__': main()
