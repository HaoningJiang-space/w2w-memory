"""Replay construction, verify frozen choices and paired holdout comparisons."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from matching_placement import contoured,ReticleService
from cycle_configurations import primal_audit
from nonuniform_pooling import units,digest,CirculationSearch,DENOMINATOR
from run_cycle_configuration_gate import activity_sets,KINDS


def apply_move(q,move):
    n=len(q);cycle=move['cycle'];cs=np.array(cycle[::2]);ms=np.array(cycle[1::2])-n
    result=q.copy();delta=move['step']*move['sign']
    result[cs,ms]+=delta;result[cs,np.roll(ms,1)]-=delta
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('input');parser.add_argument('--output',required=True)
    args=parser.parse_args();path=Path(args.input)
    raw=gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_bytes()
    data=json.loads(raw);p=contoured();explicit=ReticleService(p)
    testing=activity_sets(range(data['test_seeds'][0],data['test_seeds'][1]+1))
    summary=dict(source_commit=data['commit'],host=data['host'],raw_sha256=hashlib.sha256(raw).hexdigest(),
        rows=[],comparisons=[],search=[],local_explicit_checks=0,max_local_error=0.,replayed_proposals=0,
        max_resource_residual=max(r['resource_residual'] for r in data['results']),
        remote_explicit_checks=sum(len(r['explicit_checks']) for r in data['results']),
        max_remote_error=max(c['error'] for r in data['results'] for c in r['explicit_checks']))
    for design in data['designs']:
        kind=design['kind'];candidates={v['name']:v for v in design['candidates']}
        constraint=CirculationSearch(p,np.ones((1,36),bool))
        for candidate in candidates.values():
            a=np.array(candidate['layout']);assert digest(a)==candidate['layout_sha256']
            assert constraint.valid(units(a));primal_audit(p,a,np.ones(36),range(36))
        q=units(candidates[design['starting_candidate']]['layout']);support=q>0
        for stage in ('ratios','joint'):
            count=0
            for step in design[f'{stage}_trace']:
                for tested in step['tested']:
                    trial=apply_move(q,tested);assert constraint.valid(trial)
                    if stage=='ratios':assert np.array_equal(trial>0,support)
                    assert digest(trial/DENOMINATOR)==tested['layout_sha256']
                    primal_audit(p,trial/DENOMINATOR,np.ones(36),range(36))
                    summary['replayed_proposals']+=1
                if step['accepted']:
                    assert step['training_mean']>step['starting_mean']+1e-7
                    q=apply_move(q,step['move']);count+=1
                    assert digest(q/DENOMINATOR)==step['layout_sha256']
                    np.testing.assert_array_equal(q,units(candidates[f'{stage}_step{count}']['layout']))
                else:assert max(t['training_mean'] for t in step['tested'])<=step['starting_mean']+1e-7
            summary['search'].append(dict(kind=kind,stage=stage,accepted=count,
                rounds=len(design[f'{stage}_trace']),starting_candidate=design['starting_candidate']))
        baseline=[v for v in candidates.values() if not v['name'].startswith(('ratios_step','joint_step'))]
        for selected in design['selections']:
            label=selected['label'];a=np.array(selected['layout'])
            np.testing.assert_array_equal(a,np.array(candidates[selected['name']]['layout']))
            assert digest(a)==selected['layout_sha256']
            if label in ('baseline_selected','ratios_selected','joint_selected'):
                pool=baseline if label=='baseline_selected' else [v for v in candidates.values() if label=='joint_selected' or not v['name'].startswith('joint_step')]
                winner=max(pool,key=lambda v:v['validation_mean'])
                assert selected['name']==winner['name']
            for test_kind in (KINDS if data.get('mixed') else (kind,)):
                result=next(r for r in data['results'] if r['kind']==test_kind and r['label']==label)
                assert digest(a)==result['layout_sha256']
                assert abs(np.mean(result['test_means'])-result['test_mean'])<1e-12
                assert abs(np.mean(result['test_common'])-result['common_mean'])<1e-12
                for index in (0,1,2,3):
                    active=np.flatnonzero(testing[test_kind][index])
                    for objective,key in [('throughput','test_means'),('common','test_common')]:
                        ref=explicit.solve(a,active,objective,floor=1);assert ref['feasible']
                        error=abs(ref['mean']-result[key][index]);assert error<1e-8
                        summary['local_explicit_checks']+=1;summary['max_local_error']=max(summary['max_local_error'],error)
                row={key:result[key] for key in ('kind','label','test_mean','common_mean','minimum_service','worst_sample_mean')}
                row.update(selected_name=selected['name'],training_mean=selected['training_mean'],
                    validation_mean=selected['validation_mean'],layout_summary=selected['layout_summary'])
                summary['rows'].append(row)
    for kind in KINDS:
        rows={r['label']:r for r in data['results'] if r['kind']==kind}
        for label in ('ratios_selected','joint_selected'):
            for baseline in ('baseline_selected','ratios_selected'):
                if label==baseline:continue
                row=rows[label];base=rows[baseline]
                diff=np.array(row['test_means'])-base['test_means'];half=1.96*diff.std(ddof=1)/len(diff)**.5
                summary['comparisons'].append(dict(kind=kind,label=label,baseline=baseline,
                    delta=float(diff.mean()),paired_ci95=[float(diff.mean()-half),float(diff.mean()+half)],
                    relative_percent=100*(row['test_mean']/base['test_mean']-1),
                    fraction_worse=float(np.mean(diff < -1e-8)),
                    common_delta=row['common_mean']-base['common_mean']))
    Path(args.output).write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ('source_commit','raw_sha256','replayed_proposals','remote_explicit_checks','local_explicit_checks','max_local_error')},indent=2))


if __name__=='__main__':main()
