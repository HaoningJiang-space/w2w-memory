#!/usr/bin/env python3
"""Compare frozen source trees without launching another full-layer matrix.

Run on hn072 with the existing native binaries. The snapshots compare historical
encoding, all predeclared compile inputs, and exact small native execution ledgers.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

SNAPSHOT = r'''
from dataclasses import asdict,replace
import json
import tempfile
from pathlib import Path
from w2w.analysis.moe_layer import digest as system_digest
from w2w.workloads.read_trace import digest as read_digest
from w2w.workloads.cohort_replay import read_json
from w2w.workloads.moe_task_graph import compile_layer,machine,LAYER_COHORTS
from w2w.workloads.moe_partition import compile_partitioned_layer
from w2w.system.wafer_machine import from_coordinates
from w2w.experiments.run_moe_layer import write,summarize
from w2w.domain.system import mesh_system
from w2w.domain.execution import ComputeTask,ExecutionGraph,ReadAccess,ResidentObject,DataEdge
from w2w.memory.rwdl_backend import RWDLAbsolute
from w2w.network.booksim_backend import factory
from w2w.system.kernel import execute_system
from w2w.validation.system_execution import audit_system_result
import os
out={}
value={'z':[1,2.5,'中文'],'a':{'v':None}}
out['fingerprints']=[system_digest(value),read_digest(value),system_digest(float('nan'))]
try:read_digest(float('nan'))
except ValueError:out['strict_nan_rejected']=True
for wide in (False,True):
 spec,physical=from_coordinates(machine(wide=wide))
 out['machine/'+str(wide)]={'spec':asdict(spec),'physical':physical}
for cohort in LAYER_COHORTS:
 for policy in ('home','pair','four_way'):
  g,m=compile_layer(cohort=cohort,residency=policy)
  out[cohort+'/'+policy]={'graph':asdict(g),'metadata':m}
g,m=compile_partitioned_layer()
out['partition']={'graph':asdict(g),'metadata':m}
with tempfile.TemporaryDirectory() as folder:
 folder=Path(folder)
 write(folder/'io.json',value)
 out['write_bytes']=(folder/'io.json').read_text()
 import gzip
 with gzip.open(folder/'fallback.json.gz','wt') as f:json.dump(value,f)
 out['read_fallback']=read_json(folder/'fallback.json')
 for streaming in (False,True):
  spec=replace(mesh_system(1,2,flit_bytes=256,input_buffer_flits=16,injection_flits=256,
     packet_payload_bytes=4096,memory_request_bytes=4096),dram_period_ps=3760)
  spec=replace(spec,tiles=tuple(replace(t,sram_bytes=65536) for t in spec.tiles))
  graph=ExecutionGraph((ComputeTask('input','c0',2),
      ComputeTask('local','c0',3,(ReadAccess('w',0,4096),)),
      ComputeTask('remote','c1',3,(ReadAccess('w',4096,4096),))),
      (ResidentObject('w','m0',0,8192),),
      (DataEdge('to-local','input','local',8192),DataEdge('to-remote','input','remote',8192)))
  native=RWDLAbsolute(spec,streaming=streaming)
  try:
   result=execute_system(spec,graph,native=native,time_advance='boundaries',
       activation_sram_read_bytes_per_cycle=256,max_ps=5_000_000,
       network_factory=factory(binary=os.environ['W2W_BOOKSIM_BINARY'],directory=folder/str(streaming),
                               local_dma='payload_beats',cell_sideband_bits=64))
  finally:native.close()
  result['audit']=audit_system_result(result)
  result['scope']='one_routed_ffn_layer_timing'
  summary=summarize(result)
  n=result['network'];native_record=result['native']
  out['execution/'+str(streaming)]={k:result[k] for k in ('events','tasks','makespan_ps','drained_ps',
        'compute_busy_ps','sram_peak_bytes','outstanding_peak','mc_peak','sram_read_bytes','sram_read_busy_cycles','audit')}
  out['execution/'+str(streaming)]['network']={k:n[k] for k in ('link_flits','accepted_bytes','delivered_bytes',
        'rx_write_bytes','rx_write_cycles','rx_job_wait_sum_ps','source_peak_flits','rx_reserved_peak',
        'admission_rejection_attempts','final')}
  out['execution/'+str(streaming)]['native']=native_record
  out['summary/'+str(streaming)]={k:v for k,v in summary.items() if k not in ('network',)}
print(json.dumps(out,sort_keys=True,allow_nan=False))
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before',type=Path,required=True)
    p.add_argument('--after',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    records=[];trees=[]
    for source in (args.before,args.after):
        raw=subprocess.check_output([sys.executable,'-c',SNAPSHOT],cwd=source,text=True)
        trees.append(json.loads(raw))
        records.append(dict(source=str(source),commit=subprocess.check_output(
            ['git','rev-parse','HEAD'],cwd=source,text=True).strip(),snapshot_sha256=sha256(raw.encode()).hexdigest()))
    different=[k for k in trees[0].keys() | trees[1].keys() if trees[0].get(k)!=trees[1].get(k)]
    value=dict(passed=not different,source_trees=records,different_sections=different,
        sections=sorted(trees[0]),scope='two historical encodings; nine compile-only graphs and metadata; two machines; partition; I/O; exact whole/stream small native ledgers and summaries')
    args.output.write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(value))
    if different:raise SystemExit(1)


if __name__=='__main__':main()
