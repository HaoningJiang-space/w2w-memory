#!/usr/bin/env python3
"""Diagnostic wakeup census; instrument existing phases without changing time.

Observed changes are not a proof of necessary interactions or a speedup bound.
Native callbacks and failed admissions absent from saved event tables are counted
in a separate native diagnostic run, never used as candidate prediction input.
"""
import argparse, gzip, hashlib, json, os, platform, subprocess, sys
from collections import Counter
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from tools.run_interactive_compute_gate import inputs as original_inputs


def write(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs(case):
    if case!='concurrent':return original_inputs(case)
    from dataclasses import replace
    from w2w.domain.execution import ExecutionGraph
    spec,graph=original_inputs('transport');base=graph.tasks[0]
    tasks=tuple(replace(base,id='gemm'+str(i),tile=tile,
        stream=replace(base.stream,macs=base.stream.weight_data_bytes*256)) for i,tile in enumerate(('c2','c3')))
    return spec,ExecutionGraph(tasks,graph.objects)


def projected_resources(e):
    # A documented over-approximation of eligibility-related changes, not a
    # full causal state and not a certification that unchanged means safe.
    def counts(row):return tuple(sorted(row.items()))
    return (tuple(sorted((k,tuple(v)) for k,v in e.engine.items())),tuple(sorted(e.ready_tasks)),
        tuple(sorted(e.memory_candidates)),counts(e.outstanding),counts(e.mc_pool_slots),
        counts(e.network.source_occupied),counts(e.network.rx_reserved),counts(e.native.reserved),
        counts(e.native.pool_live),tuple(sorted((k,len(v)) for k,v in e.native.aggregate.items())),
        tuple(sorted((k,v.head) for k,v in e.operand_frontiers.items())))


def potential_gap(e):
    checks=dict(network_active=not e.network.native_idle,network_future=bool(e.network.future),
        network_ready=bool(e.network.ready_packets),receiver_waiters=any(e.network.receiver_waiters.values()),
        memory_queue=any(e.native.queues.values()),gateway_queue=any(e.native.aggregate.values()),
        reading=bool(e.reading),memory_candidate=bool(e.memory_candidates),
        active_edges=bool(e.active_edges),ready_task=bool(e.ready_tasks),
        no_pending_array=not bool(e.native.backend.pending))
    live=[(t,k) for t,keys in e.engine.items() for k in keys]
    checks['compute_not_funded']=True
    if len(live)==1:
        tile,key=live[0];s=e.state[key];task=e.tasks[key]
        if task.stream and s.get('stream_scale_consumed') and s['finish_ps'] is None:
            reuse=task.stream.macs//task.stream.weight_data_bytes
            rate=min(task.stream.weight_read_bytes_per_cycle,task.stream.macs_per_cycle//reuse)
            checks['compute_not_funded']=e._available_weights(key)<2*rate
    return checks


def worker(out,case,binary):
    from w2w.system.kernel import SystemExecution
    from w2w.backends.booksim.runtime.online_booksim import OnlineBookSim
    from w2w.backends.booksim.adapter import BookSimNetwork
    from w2w.backends.ramulator.adapter import VerticalRWDL
    from w2w.backends.ramulator.rwdl import RamulatorRWDL
    from tools import run_interactive_compute_gate as old
    rows=[];current=Counter();active=[False]
    def count(name,value=1):
        if active[0]:current[name]+=value
    request=OnlineBookSim._request
    def rpc(self,row):
        count('network_rpc_'+row['command']);reply=request(self,row)
        for item in reply.get('progress',()):count('network_'+item['event'])
        count('network_completed',len(reply.get('completed',())))
        return reply
    OnlineBookSim._request=rpc
    def counted(cls,name,prefix):
        function=getattr(cls,name)
        def call(self,*args,**kwargs):
            count(prefix+'_attempt');result=function(self,*args,**kwargs)
            if (result is not None if prefix=='atom_admission' else result):count(prefix+'_accepted')
            return result
        setattr(cls,name,call)
    counted(BookSimNetwork,'try_send','ni_admission')
    counted(VerticalRWDL,'submit','descriptor_admission')
    counted(RamulatorRWDL,'submit','atom_admission')
    advance=RamulatorRWDL.advance
    def dram(self,now):
        before=self.native_cycle;count('dram_host_advance')
        result=advance(self,now)
        if self.native_cycle!=before:count('dram_bridge_advance');count('dram_ticks',self.native_cycle-before)
        count('array_callbacks',len(result));return result
    RamulatorRWDL.advance=dram
    take=VerticalRWDL.take_ready
    def ready(self):
        result=take(self);count('gateway_ready_atoms',len(result));return result
    VerticalRWDL.take_ready=ready
    times=SystemExecution._times
    def clock(e,*args,**kwargs):
        for now in times(e,*args,**kwargs):
            current.clear();active[0]=True;begin=len(e.events);before=projected_resources(e)
            try:yield now
            finally:
                active[0]=False
                appended=e.events[begin:];events=Counter(r['kind'] for r in appended)
                checks=potential_gap(e)
                rows.append(dict(time_ps=now,calls=dict(current),events=dict(events),
                    resource_projection_changed=before!=projected_resources(e),
                    gap_blockers=[k for k,v in checks.items() if v]))
    SystemExecution._times=clock
    old.inputs=inputs
    old.worker(out,case,'off',binary)
    result=json.loads(gzip.open(out/'result.json.gz','rt').read())
    from w2w.validation.vertical_access import audit_vertical_result
    from w2w.validation.request_control import audit_request_control
    from w2w.validation.rwdl_commands import audit_rwdl_commands
    audit_vertical_result(result);audit_request_control(result);audit_rwdl_commands(result,out/'commands')
    periods={result['spec']['noc_period_ps'],result['spec']['dram_period_ps'],
        *(t['compute_period_ps'] for t in result['spec']['tiles'])}
    clocks={at for p in periods for at in range(0,result['drained_ps']+1,p)}
    if len(rows)!=result['kernel_iterations'] or len({r['time_ps'] for r in rows})!=len(rows):
        raise ValueError('Missing/repeated host wakeup')
    all_calls=Counter();all_events=Counter();classification=Counter();blockers=Counter()
    for row in rows:
        calls,events=row['calls'],row['events'];all_calls.update(calls);all_events.update(events)
        compute=events.get('stream_compute',0)+events.get('compute_service',0)
        external_events=sum(v for k,v in events.items() if k not in ('stream_compute','compute_service'))
        external=calls.get('network_inject',0)+calls.get('network_receive',0)+calls.get('network_completed',0)
        external+=calls.get('array_callbacks',0)+calls.get('gateway_ready_atoms',0)
        classification['with_observed_interface_progress']+=bool(external_events or external)
        classification['resource_projection_changes']+=row['resource_projection_changed']
        quiet=not external_events and not external and not row['resource_projection_changed']
        classification['no_observed_interface_or_resource_change']+=quiet
        classification['quiet_with_compute_service']+=quiet and bool(compute)
        classification['quiet_without_compute_service']+=quiet and not compute
        classification['potential_active_array_gap']+=not row['gap_blockers']
        blockers.update(row['gap_blockers'])
    with gzip.open(out/'wakeups.json.gz','wt') as stream:json.dump(rows,stream)
    write(out/'CENSUS.json',dict(complete=True,case=case,source_commit=subprocess.check_output(
        ['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),kernel_iterations=len(rows),clock_union=len(clocks),
        off_clock_wakeups=len({r['time_ps'] for r in rows}-clocks),classification=dict(classification),
        calls=dict(all_calls),appended_events=dict(all_events),gap_blockers=dict(blockers),
        makespan_ps=result['makespan_ps'],drained_ps=result['drained_ps'],
        input_sha256=sha(out/'input.json'),result_sha256=sha(out/'result.json.gz'),wakeups_sha256=sha(out/'wakeups.json.gz'),
        limits='observed changes and documented resource projection; quiet does not certify safe lookahead; instrumented wall time is not a performance result'))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path)
    p.add_argument('--binary',type=Path,required=True);p.add_argument('--worker',choices=('stable','transport','concurrent'))
    a=p.parse_args();out=a.output.resolve()
    if platform.node()!='ee4e072' or not out.is_relative_to('/Projects/haoning'):raise ValueError('Run on hn072')
    if a.worker:worker(out,a.worker,a.binary);return
    if out.exists():raise ValueError('Fresh diagnostic output required')
    out.mkdir()
    for case in ('stable','transport','concurrent'):
        child=subprocess.run(['taskset','-c','18,19',sys.executable,str(Path(__file__).resolve()),str(out/case),
            '--binary',str(a.binary),'--worker',case],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        (out/(case+'.log')).write_bytes(child.stdout)
        if child.returncode:raise RuntimeError('Preserved failed census: '+case)
        print(case,'census complete',flush=True)
    write(out/'COMPLETE.json',dict(complete=True,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        artifacts={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}))


if __name__=='__main__':main()
