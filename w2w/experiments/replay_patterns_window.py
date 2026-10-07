"""One actual routed window, unscaled full expert bytes, frozen endpoint designs."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import time

from w2w.synthesis.read_catalog import load_designs
from w2w.workloads.read_trace import ReadTrace
from w2w.service.read_replay import replay_reads,ReadReplayConfig
from w2w.service.cost import CostModel
from w2w.analysis.read_completion import completion_metrics


def worker(index,trace_record,config_record,output):
    design=load_designs()[0][index];trace=ReadTrace.from_record(trace_record)
    started=time.monotonic();row=replay_reads(design,trace,ReadReplayConfig(**config_record))
    row.update(id=design.name,cost=CostModel.evaluate(design),wall_seconds=time.monotonic()-started)
    row['completion']=completion_metrics(trace,row)
    data=gzip.compress(json.dumps(row,separators=(',',':'),allow_nan=False).encode(),mtime=0)
    path=Path(output)/f'design{index}.json.gz';path.write_bytes(data)
    return index,dict(path=path.name,sha256=sha256(data).hexdigest(),id=design.name,
        makespan_slots=row['makespan_slots'],logical_bytes=row['logical_bytes'],audit=row['audit'],
        delivery_sha256=row['delivery_sha256'],residence_sha256=row['residence_sha256'],
        wall_seconds=row['wall_seconds'],cost=row['cost'],stalls=row['stalls'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trace',required=True)
    p.add_argument('--output',required=True);p.add_argument('--workers',type=int,default=4)
    a=p.parse_args()
    if subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise RuntimeError('Clean committed source required')
    output=Path(a.output)
    if output.exists():raise ValueError('Use a new output directory')
    output.mkdir(parents=True)
    trace=ReadTrace.from_record(json.loads(Path(a.trace).read_text()))
    config=ReadReplayConfig(max_slots=200000,max_trace_words=10000000)
    words=sum(r.size_bytes for t in trace.tasks for r in t.reads)//32
    if words>config.max_trace_words:raise ValueError('Window exceeds declared word budget')
    indices=[0,1,2,4,6];results={}
    with ProcessPoolExecutor(max_workers=min(4,max(1,a.workers))) as pool:
        futures=[pool.submit(worker,i,trace.record(),asdict(config),output) for i in indices]
        for future in as_completed(futures):
            index,record=future.result();results[index]=record
            print('COMPLETE',index,record['makespan_slots'],record['wall_seconds'],flush=True)
    old=json.loads(gzip.decompress((output/results[4]['path']).read_bytes()))
    new=json.loads(gzip.decompress((output/results[6]['path']).read_bytes()))
    keys=('trace_sha256','residence_sha256','config','makespan_slots','tasks','routes','audit',
          'delivery_sha256','stalls','native_words_by_bank','peak_outstanding_words')
    if any(old[k]!=new[k] for k in keys):raise RuntimeError('Duplicated/configurable ablation differs')
    record=dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        trace_sha256=trace.sha256,config=asdict(config),logical_words=words,evidence=trace.evidence,
        results=[dict(index=i,**results[i]) for i in indices],
        ablation=dict(duplicated=4,configurable=6,equal=True,fields=list(keys)),
        scope='One real routing window with modeled full expert weight reads. Finite endpoint/request/RX service model; not full LLM latency or RTL timing.')
    (output/'summary.json').write_text(json.dumps(record,indent=2)+'\n')
    print('VERIFIED_FULL_WINDOW',words,'words',flush=True)


if __name__=='__main__':main()
