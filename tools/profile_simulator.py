#!/usr/bin/env python3
"""Profile the frozen cold FFN without changing its physical execution policy.

Inclusive wall timers overlap (not an additive stall model). cProfile is optional;
the normal measurement records phase/IPC/native-call timers and OS CPU/RSS.
"""
import argparse
from collections import defaultdict
import cProfile
import gzip
import json
from pathlib import Path
import resource
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from w2w.experiments.run_operand_access import inputs
from w2w.backends.ramulator import VerticalRWDL
from w2w.backends.ramulator.rwdl import RamulatorRWDL
from w2w.backends.booksim.adapter import factory
from w2w.backends.booksim.runtime.online_booksim import OnlineBookSim
from w2w.system.kernel import SystemExecution, execute_system
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control
from w2w.provenance import revision
from w2w.common.io import write_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--case',choices=('central-plus','distributed'),required=True)
    p.add_argument('--booksim-binary',type=Path,required=True)
    p.add_argument('--cprofile',action='store_true')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    counters=defaultdict(lambda:dict(calls=0,wall_ns=0))
    def timed(label,fn):
        def wrapped(*a,**kw):
            start=time.perf_counter_ns()
            try:return fn(*a,**kw)
            finally:
                row=counters[label];row['calls']+=1;row['wall_ns']+=time.perf_counter_ns()-start
        return wrapped
    for name in ('_allocate','_read_issue','_memory_progress','_native_progress','_receive',
                 '_data_transfers','_compute_completions','_start_compute','_stream_compute_progress','_cache_lookup_progress'):
        setattr(SystemExecution,name,timed('kernel.'+name,getattr(SystemExecution,name)))
    request=OnlineBookSim._request
    def measured_request(self,r):
        return timed('ipc.'+r['command'],request)(self,r)
    OnlineBookSim._request=measured_request
    for name in ('_receive','close'):
        setattr(OnlineBookSim,name,timed('booksim.'+name,getattr(OnlineBookSim,name)))
    init=RamulatorRWDL.__init__
    class MeasuredBridge:
        def __init__(self,impl):self.impl=impl
        def __getattr__(self,name):
            fn=getattr(self.impl,name)
            return timed('native_ramulator.'+name,fn) if callable(fn) else fn
    def measured_init(self,*a,**kw):
        init(self,*a,**kw);self.impl=MeasuredBridge(self.impl)
    RamulatorRWDL.__init__=measured_init
    for name in ('advance','submit'):
        setattr(VerticalRWDL,name,timed('vertical.'+name,getattr(VerticalRWDL,name)))
    spec,graph,data=inputs(args.case)
    write_json(args.output/'input.json',data)
    native=VerticalRWDL(spec,request_control=True)
    profile=cProfile.Profile() if args.cprofile else None
    start=time.monotonic();cpu=time.process_time()
    if profile:profile.enable()
    try:
        result=execute_system(spec,graph,native=native,compute_contexts=2,operand_readiness='contiguous_prefix',
            activation_sram_read_bytes_per_cycle=spec.rx_write_bytes_per_cycle,time_advance='boundaries',max_ps=3000000000,
            network_factory=factory(binary=args.booksim_binary,directory=args.output/'network',**data['network_policy']))
    finally:
        native.close()
        if profile:profile.disable();profile.dump_stats(str(args.output/'python.pstats'))
    execution_wall=time.monotonic()-start;execution_cpu=time.process_time()-cpu
    audit_start=time.monotonic()
    result['audit']=audit_vertical_result(result);result['control_audit']=audit_request_control(result)
    audit_seconds=time.monotonic()-audit_start
    save=time.monotonic()
    with gzip.open(args.output/'result.json.gz','wt',compresslevel=3) as f:json.dump(result,f)
    children=resource.getrusage(resource.RUSAGE_CHILDREN);own=resource.getrusage(resource.RUSAGE_SELF)
    record=dict(schema='w2w.simulator-profile.v1',source_commit=revision(),case=args.case,
        execution_wall_seconds=execution_wall,python_process_cpu_seconds=execution_cpu,
        booksim_child_cpu_seconds=children.ru_utime+children.ru_stime,
        peak_python_rss_kib=own.ru_maxrss,peak_child_rss_kib=children.ru_maxrss,
        result_serialization_seconds=time.monotonic()-save,audit_seconds=audit_seconds,
        kernel_iterations=result['kernel_iterations'],makespan_ps=result['makespan_ps'],
        event_count=len(result['events']),timers=dict(counters),complete=True,
        booksim_sha256=result['network']['identity']['binary_sha256'],bridge_sha256=result['native']['bridge_sha256'],
        timer_contract='inclusive wall timers; nested intervals overlap; child CPU is independent process CPU, not additive wall stall; measurement overhead included',
        audit=result['audit'],control_audit=result['control_audit'])
    write_json(args.output/'profile.json',record);print(json.dumps(record),flush=True)


if __name__=='__main__':main()
