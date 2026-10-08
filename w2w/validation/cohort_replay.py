"""Reconstruct logical inputs and audit finite completion independently of fitting."""
import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

from w2w.analysis.service_provisioning import provisioning_certificate, check_provisioning_bound
from w2w.provenance import provenance
from w2w.service.cost import CostModel
from w2w.service.read_replay import ReadReplayConfig, design_record
from w2w.synthesis.cohort_replay import designs
from w2w.synthesis.read_catalog import archived_cost_matches
from w2w.validation.patterns_replay import check_delivery, check_frozen_accounting, check_routing_union
from w2w.workloads.cohort_replay import (METHOD, OLD_INPUTS, PROBE_SHA, STRUCTURES, read_json,
    frozen_owners, select_requests, cases, jobs, owner_key, logical_signature)
from w2w.workloads.patterns_trace import compile_patterns_window, load_requests
from w2w.workloads.read_trace import ReadTrace, ReadObject, ReadTask, ReadSpan, digest

EQUAL_FIELDS=('trace_sha256','residence_sha256','config','makespan_slots','tasks','routes',
              'audit','delivery_sha256','stalls','native_words_by_bank','peak_outstanding_words')


def check_trace(trace, case, routes, owners, weight_bytes=18878976):
    """Build expected objects/tasks from frozen token selections, not the compiler."""
    selected={e for key in case['requests'] for e in routes[key]['decode'][case['decode_step']-1][0]}
    objects=tuple(ReadObject(f'layer:0/expert:{e}',weight_bytes,c) for e,c in enumerate(owners))
    tasks=tuple(ReadTask(f'batch0/layer0/expert{e}',owners[e],
                        (ReadSpan(f'layer:0/expert:{e}',0,weight_bytes),)) for e in sorted(selected))
    expected=ReadTrace(objects,(*tasks,ReadTask('batch0/layer0/join',None,
                        dependencies=tuple(t.id for t in tasks))),'captured',trace.source)
    if trace.sha256!=expected.sha256:
        raise ValueError('Objects, owners, selected bytes or task DAG changed')
    return selected


def audit_inputs(source, verify_raw=False):
    source=Path(source)
    summary=read_json(source/'summary.json')
    if (summary['schema']!='w2w.cohort-replay-input.v1' or summary['provenance']['git_status']
            or summary['registration_sha256']!=sha256(METHOD.read_bytes()).hexdigest()
            or summary['probe_sha256']!=PROBE_SHA):
        raise ValueError('Input source/registration changed')
    paths=[r['path'] for r in summary['files']]
    if len(paths)!=len(set(paths)):
        raise ValueError('Duplicate input file')
    for item in summary['files']:
        raw=(source/item['path']).read_bytes()
        if len(raw)!=item['bytes'] or sha256(raw).hexdigest()!=item['sha256']:
            raise ValueError('Frozen input hash changed')
    corpus=read_json(source/'corpus_manifest.json')
    old=read_json(OLD_INPUTS/'summary.json')
    if sha256((source/'corpus_manifest.json').read_bytes()).hexdigest()!=old['source_manifest_sha256']:
        raise ValueError('Unexpected corpus')
    split=select_requests(corpus,old)
    if split!=summary['split'] or list(map(len,split['groups']))!=[16]*3 or len(split['excluded'])!=160:
        raise ValueError('Fresh request split changed')
    owners=frozen_owners()
    if read_json(source/'owners.json')!=owners:
        raise ValueError('Frozen training mapping changed')
    extracted=read_json(source/'routes.json.gz')
    if [r['id'] for r in extracted]!=sum(split['groups'],[]):
        raise ValueError('Extracted routing coverage changed')
    routes={r['id']:r for r in extracted}
    originals={r['id']:r for r in corpus['requests']}
    for r in extracted:
        if (r['source']['sha256']!=originals[r['id']]['sha256'] or len(r['decode'])!=128
                or any(len(s)!=1 or len(s[0])!=8 or len(set(s[0]))!=8
                       or any(type(e)!=int or not 0<=e<128 for e in s[0]) for s in r['decode'])):
            raise ValueError('Malformed or wrong source routing')
    base=read_json(OLD_INPUTS/'training_spec.json')
    base['layers']=[dict(base['layers'][0],compute_by_expert=owners['marginal'])]
    if verify_raw:
        raw_requests,_=load_requests(source/'raw_manifest.json',base)
        if digest([dict(id=r.id,source=r.source,decode=r.decode) for r in raw_requests])!=digest(extracted):
            raise ValueError('Extracted routes differ from raw files')
    expected=cases(split)
    if len(summary['cases'])!=9 or [c['id'] for c in summary['cases']]!=[c['id'] for c in expected]:
        raise ValueError('Input case coverage changed')
    traces={}
    for case, required in zip(summary['cases'],expected,strict=True):
        if any(case[k]!=v for k,v in required.items()):
            raise ValueError('Input case selection changed')
        folder=source/case['id']
        manifest=read_json(folder/'manifest.json')
        if [r['id'] for r in manifest['requests']]!=case['requests']:
            raise ValueError('Case source selection changed')
        for r in manifest['requests']:
            if r['sha256']!=originals[r['id']]['sha256'] or r['arrival_iteration']!=0:
                raise ValueError('Case raw source identity changed')
        for name,assignment in owners.items():
            spec=read_json(folder/f'{name}_spec.json')
            required_spec=deepcopy(base)
            required_spec['batching']['batch_size']=case['batch_size']
            required_spec['layers'][0]['compute_by_expert']=assignment
            if spec!=required_spec:
                raise ValueError('Execution spec changed')
            trace=ReadTrace.from_record(read_json(folder/f'{name}_trace.json'))
            demand=read_json(folder/f'{name}_demand.json')
            selected=check_trace(trace,case,routes,assignment)
            count=Counter(e for key in case['requests'] for e in routes[key]['decode'][case['decode_step']-1][0])
            if (logical_signature(trace)!=case['logical_signature'] or demand['trace_sha256']!=trace.sha256
                    or demand['total_logical_read_bytes']!=len(selected)*18878976
                    or demand['total_logical_read_bytes']!=case['logical_bytes']
                    or case['distinct_experts']!=len(selected)
                    or demand['total_resident_weight_bytes']!=128*18878976
                    or {int(k):v for k,v in demand['windows'][0]['expert_token_counts'].items()}!=dict(count)):
                raise ValueError('Logical identity or demand accounting changed')
            if verify_raw:
                rebuilt,_=compile_patterns_window(folder/'manifest.json',spec,case['decode_step'])
                if rebuilt.sha256!=trace.sha256:
                    raise ValueError('Raw recompilation differs')
                check_routing_union(folder/'manifest.json',spec,case['decode_step'],demand)
            traces[case['id'],name]=trace
    return summary,traces


def audit(source, inputs):
    source,inputs=Path(source),Path(inputs)
    frozen,traces=audit_inputs(inputs)
    summary=read_json(source/'summary.json')
    if (summary['schema']!='w2w.cohort-replay-results.v1' or summary['provenance']['git_status']
            or summary['registration_sha256']!=sha256(METHOD.read_bytes()).hexdigest()
            or summary['inputs_sha256']!=sha256((inputs/'summary.json').read_bytes()).hexdigest()):
        raise ValueError('Replay source/input identity changed')
    keys=[(r['case'],r['label'],r['mode']) for r in summary['results']]
    if len(keys)!=len(set(keys)) or set(keys)!=set(jobs()) or {tuple(k) for k in summary['jobs']}!=set(jobs()):
        raise ValueError('Replay coverage changed')
    hardware=designs()
    cfg=ReadReplayConfig(outstanding_words_per_compute=192,rx_depth_words=3,max_trace_words=80000000,max_slots=500000)
    observed={}
    for item in summary['results']:
        case,label,mode=item['case'],item['label'],item['mode']
        raw=(source/item['path']).read_bytes()
        if (item['path']!=f'{case}/{label}_{mode}.json.gz' or len(raw)!=item['bytes']
                or sha256(raw).hexdigest()!=item['sha256']):
            raise ValueError('Replay file hash/path changed')
        row=read_json(source/item['path'])
        trace=traces[case,owner_key(label,mode)]
        design=hardware[label]
        if (digest(row['config'])!=digest(asdict(cfg)) or digest(row['design'])!=digest(design_record(design))
                or row['trace_sha256']!=trace.sha256 or not archived_cost_matches(CostModel.evaluate(design),row['cost'])):
            raise ValueError('Replay configuration/hardware/cost changed')
        cert=provisioning_certificate(design,trace,cfg)
        check_delivery(trace,row)
        check_frozen_accounting(cert['word_certificate'],row,trace.word_bytes)
        if digest(check_provisioning_bound(cert,row))!=digest(row['provisioning_bound']):
            raise ValueError('Resource bound changed')
        for field in ('trace_sha256','design_sha256','residence_sha256','makespan_slots','logical_bytes',
                      'audit','delivery_sha256','cost','provisioning_bound','wall_seconds'):
            if digest(item[field])!=digest(row[field]):
                raise ValueError('Summary differs from raw replay')
        observed[case,label,mode]=row
    for case in frozen['cases']:
        left,right=(observed[case['id'],k,'cohort'] for k in ('c','c_dup'))
        if any(digest(left[k])!=digest(right[k]) for k in EQUAL_FIELDS):
            raise ValueError('Duplicated/configurable service differs')
        for label in STRUCTURES:
            a,b=(observed[case['id'],label,m] for m in ('marginal','cohort'))
            if a['design_sha256']!=b['design_sha256'] or digest(a['cost'])!=digest(b['cost']):
                raise ValueError('Mapping comparison changed hardware')
    words=sum(row['audit']['delivered_words'] for row in observed.values())
    if words!=summary['delivered_words']:
        raise ValueError('Word total changed')
    return dict(verified=True,provenance=provenance(),source_commit=summary['provenance']['commit'],
        records=len(keys),delivered_words=words,fresh_requests=48,excluded_requests=160,windows=9,
        identical_ablations=9,raw_inputs_recompiled=False,
        scope='Full modeled read completion and independent resource accounting, not native DRAM or application execution')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',required=True);p.add_argument('--source');p.add_argument('--output',required=True)
    p.add_argument('--verify-raw',action='store_true')
    a=p.parse_args()
    if a.source:
        result=audit(a.source,a.inputs)
    else:
        summary,traces=audit_inputs(a.inputs,a.verify_raw)
        result=dict(verified=True,provenance=provenance(),traces=len(traces),fresh_requests=48,
                    raw_inputs_recompiled=a.verify_raw,input_source_commit=summary['provenance']['commit'])
    Path(a.output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
