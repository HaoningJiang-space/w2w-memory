#!/usr/bin/env python3
"""Run one old/new cold FFN with complete command and endpoint trace fingerprints.

The tool lives outside the measured source tree; --source selects the frozen
implementation. Trace hashing is identical on both sides, including disabled
protocol logs. Hardware events are retained; only diagnostic serialization is
avoided. This is not an approximate simulation mode.
"""
import argparse,gzip,hashlib,json,resource,sys,time,os
from pathlib import Path
from types import SimpleNamespace


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--case',choices=('central-plus','distributed'),required=True)
    p.add_argument('--booksim-binary',type=Path,required=True);p.add_argument('--small',action='store_true')
    args=p.parse_args();args.source=args.source.resolve();args.output=args.output.resolve()
    sys.path.insert(0,str(args.source));os.chdir(args.source);args.output.mkdir(parents=True,exist_ok=False)
    from w2w.experiments.run_operand_access import inputs
    from w2w.workloads.moe import build_moe
    from w2w.mapping.data_placement import place_weights
    from w2w.mapping.compute_placement import place_compute
    from w2w.mapping.lowering import lower
    from w2w.backends.ramulator import VerticalRWDL
    from w2w.backends.ramulator.rwdl import RamulatorRWDL
    from w2w.backends.booksim.adapter import factory
    from w2w.backends.booksim.runtime.online_booksim import OnlineBookSim
    from w2w.system.kernel import execute_system
    from w2w.validation.vertical_access import audit_vertical_result
    from w2w.validation.request_control import audit_request_control
    from w2w.validation.rwdl_commands import audit_rwdl_commands
    from w2w.provenance import revision
    spec,graph,data=inputs(args.case)
    if args.small:
        logical=build_moe(((0,),),experts=4,topk=1,intermediate=512)
        weights=place_weights(logical,spec.stack)
        graph,_=lower(logical,spec,weights,place_compute(logical,spec.stack,weights))
    h=hashlib.sha256();counts=dict(mutations=0,progress=0,completed=0)
    request=OnlineBookSim._request
    def observed(self,r):
        if r['command'] in ('submit','supply','commit','boundary'):
            h.update(json.dumps(dict(request=r),sort_keys=True,separators=(',',':')).encode()+b'\n');counts['mutations']+=1
        reply=request(self,r)
        for kind in ('progress','completed'):
            for event in reply.get(kind,()):
                h.update(json.dumps({kind:event},sort_keys=True,separators=(',',':')).encode()+b'\n');counts[kind]+=1
        return reply
    OnlineBookSim._request=observed
    policy=spec.stack.native_policy
    profile=SimpleNamespace(controller=policy,timing=SimpleNamespace(**{k:v for k,v in vars(policy).items() if k.startswith('n')}))
    backend=RamulatorRWDL(len(spec.stack.memory_regions),domain_count=len(spec.stack.dram_domains),
        array_bytes=spec.stack.dram_domains[0].capacity_bytes,profile=profile,refresh=True,command_trace=args.output/'commands')
    native=VerticalRWDL(spec,request_control=True,backend=backend);start=time.monotonic()
    try:
        result=execute_system(spec,graph,native=native,compute_contexts=2,operand_readiness='contiguous_prefix',
            activation_sram_read_bytes_per_cycle=spec.rx_write_bytes_per_cycle,time_advance='boundaries',max_ps=3000000000,
            network_factory=factory(binary=args.booksim_binary,directory=args.output/'network',**data['network_policy']))
    finally:native.close()
    elapsed=time.monotonic()-start
    result['audit']=audit_vertical_result(result);result['control_audit']=audit_request_control(result)
    command_audit=audit_rwdl_commands(result,args.output/'commands')
    with gzip.open(args.output/'result.json.gz','wt',compresslevel=3) as f:json.dump(result,f)
    command_hash=hashlib.sha256()
    for path in sorted(args.output.glob('commands.ch*')):command_hash.update(path.name.encode());command_hash.update(path.read_bytes())
    own=resource.getrusage(resource.RUSAGE_SELF);child=resource.getrusage(resource.RUSAGE_CHILDREN)
    record=dict(complete=True,source_commit=revision(),case=args.case,small=args.small,
        execution_wall_seconds=elapsed,total_wall_seconds=time.monotonic()-start,
        makespan_ps=result['makespan_ps'],drained_ps=result['drained_ps'],events=len(result['events']),
        endpoint_trace_sha256=h.hexdigest(),endpoint_trace_counts=counts,commands_sha256=command_hash.hexdigest(),
        command_audit=command_audit,audit=result['audit'],control_audit=result['control_audit'],
        peak_rss_kib=own.ru_maxrss,child_cpu_seconds=child.ru_utime+child.ru_stime,
        measurement='same-host command recorder plus endpoint trace hashing on both implementations; instrumentation included; integer-ps execution and full physical record separately compared')
    (args.output/'completion.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n');print(json.dumps(record),flush=True)


if __name__=='__main__':main()
