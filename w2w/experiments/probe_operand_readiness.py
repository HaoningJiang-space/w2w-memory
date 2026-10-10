"""Four small complete native FFNs to bound sensitivity to descriptor-ready policy."""
import argparse,gzip,json,time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from w2w.architecture.presets import vertical_memory
from w2w.architecture.compiler import compile_machine
from w2w.workloads.moe import build_moe
from w2w.mapping.data_placement import place_weights
from w2w.mapping.compute_placement import place_compute
from w2w.mapping.lowering import lower
from w2w.backends.ramulator import VerticalRWDL
from w2w.backends.booksim.adapter import factory
from w2w.system.kernel import execute_system
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control
from w2w.common.io import write_json
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.provenance import revision


def holes(result):
    ranges={};head=Counter();received=Counter();peak=Counter();nonprefix_events=0
    for e in result['events']:
        if e['kind']!='stream_operand_ready':continue
        key=e['task'];rule=next(t['stream'] for t in result['graph']['tasks'] if t['id']==key)
        start=e['object_offset']
        if start>=rule['weight_data_bytes']:continue
        row=ranges.setdefault(key,{})
        row[start]=start+e['bytes'];received[key]+=e['bytes']
        while head[key] in row:head[key]=row[head[key]]
        lag=received[key]-head[key];peak[key]=max(peak[key],lag)
        if lag:nonprefix_events+=1
    return dict(deliveries_with_a_prefix_hole=nonprefix_events,max_nonprefix_committed_bytes=max(peak.values(),default=0),
        tasks_with_a_hole=sum(v>0 for v in peak.values()),scope='arrival opportunities, not additive critical-path stalls')


def run(output,binary):
    output.mkdir(parents=True,exist_ok=False);rows={};frozen=None
    logical=build_moe(((0,1),),experts=4,topk=2,intermediate=512)
    for organization in ('central','distributed'):
        machine=compile_machine(vertical_memory(organization));weights=place_weights(logical,machine.stack)
        graph,meta=lower(logical,machine,weights,place_compute(logical,machine.stack,weights))
        if frozen is not None and graph!=frozen:raise ValueError('Readiness comparison changed mapping/work')
        frozen=graph
        for policy in ('byte_count','contiguous_prefix'):
            name=organization+'-'+policy;directory=output/name;directory.mkdir()
            data=dict(machine=asdict(machine.stack),graph=asdict(graph),logical=asdict(logical),metadata=meta,
                compute_contexts=2,operand_readiness=policy,request_control=True,refresh=False,
                network_policy=dict(ready_router_ids=tuple(r.id for r in machine.stack.routers),ready_slots=16))
            write_json(directory/'input.json',data);native=VerticalRWDL(machine,request_control=True,refresh=False);start=time.monotonic()
            try:
                r=execute_system(machine,graph,native=native,compute_contexts=2,operand_readiness=policy,
                    time_advance='boundaries',max_ps=1000000000,
                    activation_sram_read_bytes_per_cycle=machine.rx_write_bytes_per_cycle,
                    network_factory=factory(binary=binary,directory=directory/'network',**data['network_policy']))
            finally:native.close()
            audit=audit_vertical_result(r);control=audit_request_control(r)
            with gzip.open(directory/'result.json.gz','wt',compresslevel=3) as f:json.dump(r,f)
            summary=dict(case=name,makespan_ps=r['makespan_ps'],makespan_us=r['makespan_ps']/1e6,input_sha256=digest(data),
                audit=audit,control_audit=control,macs=meta['macs'],vector_ops=meta['vector_ops'],
                arithmetic_busy_ps=sum(r['compute_busy_ps'].values()),native_config_sha256=r['native']['config_sha256'],
                hop_flits=sum(r['network']['link_flits'].values()),operand_readiness=r['operand_readiness'],
                committed_holes=holes(r),sram_peak_bytes=r['sram_peak_bytes'],binary_sha256=r['network']['identity']['binary_sha256'],
                wall_seconds=time.monotonic()-start,source_commit=revision())
            write_json(directory/'completion.json',summary);rows[name]=summary
            print(json.dumps(dict(case=name,makespan_us=summary['makespan_us'],holes=summary['committed_holes'])),flush=True)
    changes={}
    for organization in ('central','distributed'):
        a,b=rows[organization+'-byte_count'],rows[organization+'-contiguous_prefix']
        for key in ('macs','vector_ops','native_config_sha256','binary_sha256'):
            if a[key]!=b[key]:raise ValueError('Readiness probe changed service/work')
        if a['audit']['native_bytes']!=b['audit']['native_bytes']:raise ValueError('Operand policy changed required bytes')
        changes[organization]=dict(delta_ps=b['makespan_ps']-a['makespan_ps'],completion_change_percent=100*(b['makespan_ps']/a['makespan_ps']-1))
    report=dict(schema='w2w.operand-readiness-probe.v1',passed=True,source_commit=revision(),cases=rows,changes=changes,
        scope='one small complete FFN, 2 experts, 512 intermediate, 2 contexts; native arrays, physical command/ACK, real BookSim; refresh disabled; no cache',
        limits='small timing-policy probe, not multi-layer or full-size sensitivity proof; byte count assumes aggregate out-of-order consumption, prefix bitmap state charged')
    write_json(output/'analysis.json',report)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--booksim-binary',type=Path,required=True);args=p.parse_args()
    run(args.output,args.booksim_binary)

if __name__=='__main__':main()
