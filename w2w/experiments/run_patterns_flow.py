"""Authorized raw routing -> modeled read DAG -> finite endpoint/HB replay."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from w2w.workloads.patterns_trace import compile_patterns


def prepare(manifest_path,spec,selected,out):
    out.mkdir(parents=True)
    original=Path(manifest_path).resolve();manifest=json.loads(original.read_text())
    manifest['requests']=[dict(r,path=os.path.relpath(original.parent/r['path'],out.resolve()))
                          for r in manifest['requests'][:selected]]
    if len(manifest['requests'])!=selected:raise ValueError('Insufficient independent requests')
    path=out/'manifest.json';path.write_text(json.dumps(manifest,indent=2)+'\n')
    spec=json.loads(json.dumps(spec));spec['batching'].update(batch_size=selected,max_decode_steps=1)
    trace,demand=compile_patterns(path,spec)
    if len(demand['windows'])!=1:raise ValueError('Expected exactly one selected-layer decode window')
    if demand['total_logical_read_bytes']//32>10000000:raise ValueError('Registered word budget exceeded')
    (out/'trace.json').write_text(json.dumps(trace.record(),indent=2)+'\n')
    (out/'demand.json').write_text(json.dumps(demand,indent=2)+'\n')
    (out/'spec.json').write_text(json.dumps(spec,indent=2)+'\n')
    return trace,demand


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--single-manifest',required=True);p.add_argument('--corpus-manifest',required=True)
    p.add_argument('--spec',default='artifacts/provenance/patterns_trace_input/execution.json')
    p.add_argument('--output',required=True);p.add_argument('--workers',type=int,default=2)
    a=p.parse_args()
    if subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise RuntimeError('Clean source required')
    output=Path(a.output)
    if output.exists():raise ValueError('Use new flow output directory')
    output.mkdir(parents=True)
    spec=json.loads(Path(a.spec).read_text())
    rows=[]
    for name,source,count in [('batch1',a.single_manifest,1),('batch2',a.corpus_manifest,2)]:
        trace,demand=prepare(source,spec,count,output/name)
        cmd=[sys.executable,'-m','w2w.experiments.replay_patterns_window','--trace',str(output/name/'trace.json'),
             '--output',str(output/name/'replay'),'--workers',str(a.workers)]
        print('BEGIN_FULL_BYTES',name,demand['total_logical_read_bytes'],flush=True)
        with (output/name/'replay.log').open('w') as log:
            child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
            (output/name/'replay.pid').write_text(str(child.pid)+'\n')
            if child.wait():raise RuntimeError('Replay failed; inspect '+str(output/name/'replay.log'))
        replay=json.loads((output/name/'replay/summary.json').read_text())
        if replay['trace_sha256']!=trace.sha256:raise RuntimeError('Replay input identity changed')
        for row in replay['results']:
            if row['logical_bytes']!=demand['total_logical_read_bytes']:raise RuntimeError('Raw-to-delivered byte mismatch')
            if row['audit']['delivered_words']*32!=demand['total_logical_read_bytes']:raise RuntimeError('Delivery mismatch')
        rows.append(dict(case=name,raw_requests=demand['requests'],trace_sha256=trace.sha256,
                         total_read_bytes=demand['total_logical_read_bytes'],replay=replay))
        print('END_VERIFIED',name,flush=True)
    (output/'summary.json').write_text(json.dumps(dict(source_commit=subprocess.check_output(
        ['git','rev-parse','HEAD'],text=True).strip(),cases=rows,
        scope='Two independent full-size routed read-window validations. Batch1 and batch2 use different requests; not a controlled batch-size performance comparison.'),indent=2)+'\n')


if __name__=='__main__':main()
