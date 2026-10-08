"""Paired task-completion effects of frozen mappings, not training objectives."""
import argparse
import csv
import json
from math import exp,log
from pathlib import Path

from w2w.workloads.cohort_replay import STRUCTURES, BATCHES, read_json, jobs


def summarize(source):
    summary=read_json(Path(source)/'summary.json')
    indexed={(r['case'],r['label'],r['mode']):r for r in summary['results']}
    if set(indexed)!=set(jobs()) or len(summary['results'])!=81:
        raise ValueError('Expected complete registered replay coverage')
    metrics=[]
    for g in range(3):
        for batch in BATCHES:
            case=f'c{g}_b{batch}'
            home=indexed[case,'home','cohort']['makespan_slots']
            wide=indexed[case,'wide','cohort']['makespan_slots']
            for label in STRUCTURES:
                before=indexed[case,label,'marginal']['makespan_slots']
                after=indexed[case,label,'cohort']['makespan_slots']
                row=indexed[case,label,'cohort']
                metrics.append(dict(case=case,batch=batch,structure=label,marginal_slots=before,
                    cohort_slots=after,same_hardware_speedup=before/after,
                    time_reduction_percent=100*(1-after/before),
                    speedup_over_optimized_home=home/after,
                    retained_optimized_wide_gain=((home/after-1)/(home/wide-1) if wide<home else None),
                    logical_bytes=row['logical_bytes'],lower_slots=row['provisioning_bound']['lower_slots']))
    def group(rows):
        return dict(windows=len(rows),faster=sum(r['cohort_slots']<r['marginal_slots'] for r in rows),
            tied=sum(r['cohort_slots']==r['marginal_slots'] for r in rows),
            slower=sum(r['cohort_slots']>r['marginal_slots'] for r in rows),
            geometric_mean_speedup=exp(sum(log(r['same_hardware_speedup']) for r in rows)/len(rows)),
            min_speedup=min(r['same_hardware_speedup'] for r in rows),
            max_speedup=max(r['same_hardware_speedup'] for r in rows),
            sum_marginal_slots=sum(r['marginal_slots'] for r in rows),
            sum_cohort_slots=sum(r['cohort_slots'] for r in rows))
    aggregates={label:dict(all=group([r for r in metrics if r['structure']==label]),
        by_batch={str(b):group([r for r in metrics if r['structure']==label and r['batch']==b]) for b in BATCHES})
        for label in STRUCTURES}
    return dict(metrics=metrics,aggregates=aggregates,
        source_commit=summary['provenance']['commit'],elapsed_seconds=summary['elapsed_seconds'],
        delivered_words=summary['delivered_words'],
        scope='Nine registered layer0 cold-read windows; independent requests, correlated nested batches; no full inference claim')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    result=summarize(a.source)
    (out/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    with (out/'paired_times.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(result['metrics'][0]));writer.writeheader();writer.writerows(result['metrics'])
    print(json.dumps(result['aggregates'],indent=2))
