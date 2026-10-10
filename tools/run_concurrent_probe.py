#!/usr/bin/env python3
"""Small native FFN S0/S1 probe with saved Gateway service and operand evidence."""
import argparse,gzip,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from w2w.architecture.presets import vertical_memory
from w2w.architecture.compiler import compile_machine
from w2w.workloads.moe import build_moe
from w2w.mapping.static_weights import static_weights
from w2w.mapping.compute_placement import place_compute
from w2w.mapping.lowering import lower
from w2w.backends.ramulator import VerticalRWDL
from w2w.backends.booksim.adapter import factory
from w2w.system.kernel import execute_system
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control
from w2w.analysis.ffn_stages import stages
from w2w.provenance import revision


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--booksim-binary',type=Path,default=os.getenv('W2W_BOOKSIM_BINARY'));a=p.parse_args()
    a.output.mkdir(exist_ok=False);spec=compile_machine(vertical_memory())
    logical=build_moe(((0,),),experts=4,topk=1,hidden=1024,intermediate=512)
    anchor=static_weights(logical,spec.stack,'reference');placement=place_compute(logical,spec.stack,anchor);cases={}
    for execution in ('s0','s1'):
        for policy in ('reference','phase-split'):
            case=execution+'-'+policy;directory=a.output/case;directory.mkdir()
            weights=static_weights(logical,spec.stack,policy);graph,meta=lower(logical,spec,weights,placement,execution_policy=execution)
            native=VerticalRWDL(spec,refresh=True,request_control=True,gateway_trace_bin_ps=100000)
            try:
                result=execute_system(spec,graph,native=native,compute_contexts=2,fetch_contexts=2 if execution=='s1' else 0,
                    read_issue_policy='round_robin' if execution=='s1' else 'ordered',operand_readiness='contiguous_prefix',
                    activation_sram_read_bytes_per_cycle=128,time_advance='boundaries',max_ps=1000000000,
                    network_factory=factory(binary=a.booksim_binary,directory=directory/'network',
                        ready_router_ids=tuple(r.id for r in spec.routers),ready_slots=16))
            finally:native.close()
            audit=audit_vertical_result(result);control=audit_request_control(result);analysis=stages(result)
            if sum(e.get('macs',0) for e in result['events'] if e['kind']=='stream_compute')!=meta['macs']:raise ValueError('Arithmetic work changed')
            result['source_commit']=revision()
            with gzip.open(directory/'result.json.gz','wt',compresslevel=3) as f:json.dump(result,f)
            cases[case]=dict(makespan_ps=result['makespan_ps'],audit=audit,control_audit=control,
                projection_pairs=analysis['projection_pairs'],last_native_tail_ps=result['native']['native_last_tail_ps'],
                gateway_bytes=result['native']['gateway_bytes'],gateway_service_bins=result['native']['gateway_service_bins'],
                booksim_sha256=result['network']['identity']['binary_sha256'],bridge_sha256=result['native']['bridge_sha256'])
    output=dict(schema='w2w.concurrent-ffn-probe.v1',passed=True,source_commit=revision(),
        shape=dict(hidden=1024,intermediate=512,block_width=128,experts=4,topk=1,partitions=4),cases=cases,
        scope='Small native execution/mechanism check; full matrix storage, same compute/native/data budgets, not full-size application speedup')
    (a.output/'analysis.json').write_text(json.dumps(output,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(passed=True,makespan_ps={k:v['makespan_ps'] for k,v in cases.items()},
        fetch_window_overlap_ps={k:v['projection_pairs']['e0/b0']['fetch_window_overlap_ps'] for k,v in cases.items()})))


if __name__=='__main__':main()
