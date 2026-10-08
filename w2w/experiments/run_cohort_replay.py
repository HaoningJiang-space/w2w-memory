"""Execute only the registered frozen mappings on the same finite read tasks."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import gzip
from hashlib import sha256
import json
from pathlib import Path
import time

from w2w.analysis.service_provisioning import provisioning_certificate, check_provisioning_bound
from w2w.provenance import provenance
from w2w.service.cost import CostModel
from w2w.service.read_replay import ReadReplayConfig, replay_reads
from w2w.synthesis.cohort_replay import designs
from w2w.validation.patterns_replay import check_delivery, check_frozen_accounting
from w2w.workloads.cohort_replay import METHOD, read_json, jobs, owner_key
from w2w.workloads.read_trace import ReadTrace


def config():
    return ReadReplayConfig(outstanding_words_per_compute=192,rx_depth_words=3,
                           max_trace_words=80000000,max_slots=500000)


def execute(key, source, output):
    case,label,mode=key
    started=time.monotonic()
    trace=ReadTrace.from_record(read_json(Path(source)/case/f'{owner_key(label,mode)}_trace.json'))
    design=designs()[label]
    cert=provisioning_certificate(design,trace,config())
    row=replay_reads(design,trace,config())
    check_delivery(trace,row)
    check_frozen_accounting(cert['word_certificate'],row,trace.word_bytes)
    row.update(provisioning_bound=check_provisioning_bound(cert,row),cost=CostModel.evaluate(design),
               wall_seconds=time.monotonic()-started)
    path=f'{case}/{label}_{mode}.json.gz'
    target=Path(output)/path
    target.parent.mkdir(parents=True,exist_ok=True)
    raw=gzip.compress(json.dumps(row,separators=(',',':'),allow_nan=False).encode(),mtime=0)
    temp=target.with_suffix('.part')
    temp.write_bytes(raw)
    temp.replace(target)
    return dict(case=case,label=label,mode=mode,path=path,bytes=len(raw),sha256=sha256(raw).hexdigest(),
                **{k:row[k] for k in ('trace_sha256','design_sha256','residence_sha256','makespan_slots',
                    'logical_bytes','audit','delivery_sha256','cost','provisioning_bound','wall_seconds')})


def run(source,output,workers):
    from w2w.validation.cohort_replay import audit_inputs
    prov=provenance()
    if prov['git_status'] or not 1<=workers<=12:
        raise ValueError('Clean source and 1..12 workers required')
    source,output=Path(source),Path(output)
    if output.exists():
        raise ValueError('Use a fresh output directory')
    inputs,_=audit_inputs(source)
    todo=jobs()
    if len(todo)!=81 or len(set(todo))!=81:
        raise ValueError('Replay coverage changed')
    output.mkdir(parents=True)
    started=time.monotonic()
    record=dict(schema='w2w.cohort-replay-results.v1',provenance=prov,
        registration_sha256=sha256(METHOD.read_bytes()).hexdigest(),
        inputs_sha256=sha256((source/'summary.json').read_bytes()).hexdigest(),workers=workers,jobs=todo)
    (output/'provenance.json').write_text(json.dumps(record,indent=2)+'\n')
    rows=[]
    with ProcessPoolExecutor(max_workers=workers) as pool,(output/'completed.jsonl').open('w') as journal:
        for future in as_completed([pool.submit(execute,key,str(source),str(output)) for key in todo]):
            row=future.result()
            rows.append(row)
            journal.write(json.dumps(row)+'\n'); journal.flush()
            print('COMPLETE',len(rows),'/',len(todo),row['case'],row['label'],row['mode'],row['makespan_slots'],flush=True)
    record.update(results=sorted(rows,key=lambda r:(r['case'],r['label'],r['mode'])),
        elapsed_seconds=time.monotonic()-started,delivered_words=sum(r['audit']['delivered_words'] for r in rows))
    (output/'summary.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    print('VERIFIED',len(rows),'replays;',record['delivered_words'],'words;',record['elapsed_seconds'],'seconds')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    p.add_argument('--workers',type=int,default=12)
    a=p.parse_args();run(a.source,a.output,a.workers)
