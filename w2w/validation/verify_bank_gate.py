"""Audit result provenance, frozen choices, equal demands and flow certificates."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np
from w2w.service.bank_sharing import BankFabric,circuit_cost,geometry


def verify(directory):
    out=Path(directory)
    manifest=json.loads((out/'manifest.json').read_text())
    designs=json.loads((out/'designs.json').read_text())
    rows=[json.loads(line) for line in (out/'records.jsonl').read_text().splitlines()]
    assert manifest['provenance']['git_status']==''
    assert not set(manifest['train_seeds'])&set(manifest['test_seeds'])
    n=len(manifest['test_seeds']);expected=len(designs)*(16*n+4*min(n,3))
    assert len(rows)==manifest['records']==expected
    design_by_id={d['id']:d for d in designs}
    physical={method:geometry(method) for method in manifest['placements']}
    frozen=defaultdict(set);demand_sets=defaultdict(set);scenarios=set();max_residual=0.
    for d in designs:
        chosen=d['search']['selected']
        assert chosen['training_mean_tb_s_per_active']>=max(t['training_mean_tb_s_per_active'] for t in d['search']['candidates'])-1e-9
        mask=chosen['mask'];assert all(len(ports)==d['k'] for ports in mask)
        assert circuit_cost(mask)==chosen['cost']
        fabric=BankFabric(physical[d['method']],mask)
        if d['layout_hash'] is not None:
            layout=np.array(json.loads((out/d['layout_file']).read_text()),dtype=np.int32)
            assert fabric.layout_hash(layout)==d['layout_hash']
            assert np.allclose(fabric.validate_layout(layout),d['bank_storage_gib'])
            if d['layout_mode'] in ('home_striped','static_interleaved'):
                frozen[d['method'],d['layout_mode']].add(d['layout_hash'])
            if d['layout_mode']=='home_striped':frozen['all','home'].add(d['layout_hash'])
    assert all(len(hashes)==1 for hashes in frozen.values())
    for r in rows:
        d=design_by_id[r['design_id']]
        assert r['layout_hash']==d['layout_hash']
        assert r['seed'] in manifest['test_seeds']
        scenario=(r['scope'],r['pattern'],r['fraction'],r['seed'])
        identity=(r['design_id'],)+scenario
        assert identity not in scenarios;scenarios.add(identity)
        demand_sets[scenario].add(tuple(r['demand_tb_s']))
        cut=r['cut'];total=r['throughput']['total_tb_s']
        assert abs(sum(cut['cut_components'].values())-cut['oracle_tb_s'])<1e-7
        assert total<=cut['oracle_tb_s']+1e-7
        assert abs(cut['oracle_tb_s']-cut['neighbor_bank_service_tb_s'])<1e-7
        if r['layout_mode']=='oracle':assert abs(total-cut['oracle_tb_s'])<1e-7
        assert abs(sum(r['throughput']['served_tb_s'])-total)<1e-7
        common=np.array(r['common']['served_tb_s']);demand=np.array(r['demand_tb_s'])
        assert np.allclose(common,demand*r['common']['common_completion'],atol=1e-7)
        max_residual=max(max_residual,r['throughput']['constraint_residual'],r['common']['constraint_residual'])
    assert all(len(demands)==1 for demands in demand_sets.values())
    assert max_residual<1e-7
    result=dict(records=len(rows),designs=len(designs),commit=manifest['provenance']['commit'],
                host=manifest['provenance']['host'],max_constraint_residual=max_residual,
                identical_demands=True,frozen_layouts=True,training_test_disjoint=True,
                finite_candidate_training_selection=True,lp_cut_certificates=True,oracle_equals_reachable_bank_union=True,
                legacy_cut_cases=len(manifest['legacy_cut_audit']),
                sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in [out/'records.jsonl',out/'designs.json',out/'manifest.json']})
    (out/'verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory');verify(p.parse_args().directory)
