"""All 256 original captures, all real layers/steps, actual expert M histograms."""
import argparse,json,time
from collections import Counter,defaultdict
from pathlib import Path
from w2w.workloads.patterns_adapter import load_corpus
from w2w.workloads.moe_trace import file_sha
from w2w.serving.batcher import fixed_cohorts
from w2w.common.io import write_json
from w2w.provenance import revision


def distribution(hist):
    count=sum(hist.values());work=sum(k*v for k,v in hist.items())
    def quantile(q):
        at=0
        for k,v in sorted(hist.items()):
            at+=v
            if at>=max(1,count*q):return k
    return dict(items=count,assignments=work,mean=work/count if count else None,
        p50=quantile(.5),p90=quantile(.9),p99=quantile(.99),maximum=max(hist,default=0),
        histogram={str(k):v for k,v in sorted(hist.items())})


def analyze(corpus,output):
    begin=time.monotonic();captures=tuple(load_corpus(corpus));shape=captures[0]['shape'];layers=tuple(str(i) for i in range(shape['layers']))
    results={}
    for B in (1,4,16,32,64,128):
        hist=Counter();distinct=Counter();by_layer=defaultdict(Counter);overlap=0;transitions=0;calls=0;assignments=0
        for cohort in fixed_cohorts(captures,B):
            steps={c['coverage']['decode_tokens'] for c in cohort}
            if len(steps)!=1:raise ValueError('Full decode coverage requires lifecycle-aware grouping')
            for layer in layers:
                previous=None
                for step in range(next(iter(steps))):
                    members=Counter(e for c in cohort for e in c['decode'][layer][step])
                    if sum(members.values())!=B*shape['topk']:raise ValueError('Actual token/expert work lost')
                    hist.update(members.values());by_layer[layer].update(members.values());distinct[len(members)]+=1
                    assignments+=sum(members.values());calls+=1
                    if previous is not None:
                        overlap+=sum(min(n,previous.get(e,0)) for e,n in members.items());transitions+=1
                    previous=members
        expected=sum(c['coverage']['decode_tokens']*shape['layers']*shape['topk'] for c in captures)
        if assignments!=expected:raise ValueError('Dropped/repeated real request, step or layer')
        results[str(B)]=dict(batch=B,expert_token_counts=distribution(hist),distinct_experts=distribution(distinct),
            calls=calls,assignments=assignments,per_layer={k:distribution(v) for k,v in by_layer.items()},
            consecutive_step_weighted_membership_overlap=overlap/(transitions*B*shape['topk']),
            cold_weight_bytes=sum(k*v for k,v in distinct.items())*(3*shape['hidden']*shape['intermediate']+12*(shape['hidden']//128)*(shape['intermediate']//128)),
            grouped_macs=3*assignments*shape['hidden']*shape['intermediate'],
            logical_dispatch_bytes=assignments*shape['hidden']*2,
            logical_combine_input_bytes=assignments*shape['hidden']*2)
        print(json.dumps(dict(batch=B,complete=True,calls=calls,p99=results[str(B)]['expert_token_counts']['p99'])),flush=True)
    prefill=Counter()
    for c in captures:
        for layer in layers:prefill.update(Counter(e for row in c['prefill'][layer] for e in row).values())
    r=dict(schema='w2w.real-moe-demand.v1',passed=True,source_commit=revision(),shape=shape,requests=len(captures),
        corpus_manifest_sha256=file_sha(corpus/'manifest.json'),coverage_audit_sha256=file_sha(corpus/'coverage-audit.json'),
        decode=results,prefill_per_request_expert_token_counts=distribution(prefill),wall_seconds=time.monotonic()-begin,
        contract='Complete source-order fixed request cohorts, all 94 original layers and every decode step. '
            'Prefill statistics retain all original prompt-route observations. No mean M substitution, request duplication, '
            'synthetic routing or source arrival time. Traffic is necessary logical work, not predicted execution time.')
    if output.exists():raise ValueError('Retain independent readback; use a new output')
    write_json(output,r)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--corpus',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();analyze(a.corpus,a.output)
