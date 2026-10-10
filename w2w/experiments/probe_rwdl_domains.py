"""Equal-byte native probe: eight striped RWDL domains versus one hot domain."""
import argparse,gzip,json,time
from dataclasses import asdict,replace
from pathlib import Path
from types import SimpleNamespace
from w2w.architecture.presets import vertical_memory
from w2w.architecture.compiler import compile_machine
from w2w.architecture.resources import inventory
from w2w.domain.execution import ResidentObject,ReadAccess,ComputeTask,ExecutionGraph
from w2w.backends.ramulator import VerticalRWDL
from w2w.backends.ramulator.rwdl import RamulatorRWDL
from w2w.backends.booksim.adapter import factory
from w2w.system.kernel import execute_system
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control
from w2w.validation.rwdl_commands import audit_rwdl_commands
from w2w.common.io import write_json
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.provenance import revision


def probe_machine():
    stack=vertical_memory('central');group=stack.bank_groups[0]
    # This overlapping address view shares the existing controller, port and MC
    # pool. BOTH cases get this identical stack; it creates no physical capacity.
    hot=replace(group,id='one-domain-view',domain_ids=group.domain_ids[:1])
    return compile_machine(replace(stack,bank_groups=(*stack.bank_groups,hot)))


def run(output,binary,payload_bytes=256*1024):
    if type(payload_bytes) is not int or payload_bytes<8*4096 or payload_bytes%(8*4096):
        raise ValueError('Probe payload must be a positive multiple of eight full descriptors')
    machine=probe_machine();group=machine.stack.bank_groups[0]
    if payload_bytes>min(d.capacity_bytes for d in machine.stack.dram_domains):
        raise ValueError('Hot-domain object exceeds its physical capacity')
    output.mkdir(parents=True,exist_ok=False);rows={}
    for case,memory in (('uniform-eight',group.id),('hot-one','one-domain-view')):
        directory=output/case;directory.mkdir();trace=directory/'commands.csv'
        obj=ResidentObject('payload',memory,0,payload_bytes)
        graph=ExecutionGraph((ComputeTask('read','c0',0,reads=(ReadAccess(obj.id,0,payload_bytes),)),),(obj,))
        data=dict(schema='w2w.rwdl-domain-probe-input.v1',machine=asdict(machine.stack),graph=asdict(graph),
            physical_inventory=inventory(machine.stack),payload_bytes=payload_bytes,request_control=True,refresh=True,
            operand_readiness='contiguous_prefix',compute_contexts=2,
            network_policy=dict(ready_router_ids=tuple(r.id for r in machine.stack.routers),ready_slots=16),
            scope='read-only service microcase; one requester, same finite physical machine; no application/MAC speedup claim')
        write_json(directory/'input.json',data);start=time.monotonic()
        p=machine.stack.native_policy
        profile=SimpleNamespace(controller=p,timing=SimpleNamespace(**{k:v for k,v in vars(p).items() if k.startswith('n')}))
        backend=RamulatorRWDL(len(machine.stack.memory_regions),domain_count=len(machine.stack.dram_domains),
            array_bytes=machine.stack.dram_domains[0].capacity_bytes,profile=profile,refresh=True,command_trace=trace)
        native=VerticalRWDL(machine,backend=backend,request_control=True)
        try:
            r=execute_system(machine,graph,native=native,compute_contexts=2,operand_readiness='contiguous_prefix',
                time_advance='boundaries',max_ps=1000000000,
                network_factory=factory(binary=binary,directory=directory/'network',**data['network_policy']))
        finally:native.close()  # Flush command recorder before independent audit.
        with gzip.open(directory/'result.json.gz','wt',compresslevel=3) as file:json.dump(r,file)
        audit=audit_vertical_result(r);control=audit_request_control(r);commands=audit_rwdl_commands(r,trace)
        active={int(k):v for k,v in r['native']['channel_atoms'].items() if v}
        expected_domains=8 if case=='uniform-eight' else 1
        if len(active)!=expected_domains or set(active.values())!={payload_bytes//16//expected_domains}:
            raise ValueError('Probe failed to exercise the requested domain distribution')
        if commands['active_read_domains']!=expected_domains or audit['native_bytes']!=payload_bytes:
            raise ValueError('Command and returned-byte probe counts disagree')
        period=machine.dram_period_ps;duration=r['drained_ps'];n=r['native'];g=next(g for g in machine.stack.gateways if g.id==group.gateway_id)
        per_domain={d:dict(**v,read_interface_busy_fraction=v['read_bus_cycles']*period/duration,
            refresh_budget_fraction=v['refresh_busy_cycles']*period/duration) for d,v in commands['channels'].items()}
        row=dict(case=case,source_commit=revision(),input_sha256=digest(data),machine_sha256=digest(data['machine']),
            makespan_ps=r['makespan_ps'],drained_ps=duration,wall_seconds=time.monotonic()-start,
            effective_payload_gb_s=payload_bytes*1000/r['makespan_ps'],native_bytes=audit['native_bytes'],
            physical_domains=n['physical_domain_count'],physical_capacity_bytes=n['physical_capacity_bytes'],
            native_first_tail_ps=n['native_first_tail_ps'],native_last_tail_ps=n['native_last_tail_ps'],
            native_config_sha256=n['config_sha256'],bridge_sha256=n['bridge_sha256'],booksim_sha256=r['network']['identity']['binary_sha256'],
            domain_atoms=active,command_audit=commands,audit=audit,control_audit=control,
            pressure=dict(domains=per_domain,gateway_bytes=n['gateway_bytes'],gateway_busy_cycles=n['gateway_busy_cycles'],
                gateway_busy_fraction={k:v*machine.noc_period_ps/duration for k,v in n['gateway_busy_cycles'].items()},
                gateway_queue_peak_bytes=n['gateway_queue_peak_bytes'],native_reservation_peak_atoms=n['reservation_peak_atoms'],
                queue_stall_attempts=n['queue_stall_attempts'],reservation_stall_attempts=n['reservation_stall_attempts'],
                rx_write_bytes=r['network']['rx_write_bytes'],rx_write_cycles=r['network']['rx_write_cycles'],
                rx_job_wait_sum_ps=r['network']['rx_job_wait_sum_ps'],mc_pool_peak=r['mc_pool_peak'],
                compute_busy_ps=r['compute_busy_ps'],compute_hop_flits=sum(r['network']['link_flits'].values())),
            necessary_bounds_ps=dict(native_interface=max(active.values())*period,
                active_hb_lanes=max(active.values())*period,gateway_output=payload_bytes//g.data_bytes_per_cycle*machine.noc_period_ps,
                receiver_payload=payload_bytes//machine.rx_write_bytes_per_cycle*machine.noc_period_ps),
            limits='fractions use whole drained interval; command/queue counts and summed RX job waits are not additive critical-path stalls; refresh budget can extend past drain; no WR validation')
        write_json(directory/'completion.json',row);rows[case]=row
        print(json.dumps(dict(case=case,makespan_ps=row['makespan_ps'],active_domains=expected_domains,native_bytes=payload_bytes)),flush=True)
    a,b=rows['uniform-eight'],rows['hot-one']
    # Command tracing embeds a distinct output path in otherwise equal configs.
    configs=[]
    for case in rows:
        with gzip.open(output/case/'result.json.gz','rt') as f:config=json.load(f)['native']['config']
        for controller in config['memory_system']['controllers']:
            controller['controller_plugins']=[{k:v for k,v in plugin.items() if k!='path'} for plugin in controller['controller_plugins']]
        configs.append(config)
    for field in ('machine_sha256','physical_domains','physical_capacity_bytes','native_bytes','bridge_sha256','booksim_sha256'):
        if a[field]!=b[field]:raise ValueError('Domain probe changed physical resources or required bytes')
    if configs[0]!=configs[1]:raise ValueError('Domain probe changed native service beyond trace destination')
    report=dict(schema='w2w.rwdl-domain-probe.v1',passed=True,source_commit=revision(),cases=rows,
        matched_native_service_sha256=digest(configs[0]),hot_over_uniform_time=b['makespan_ps']/a['makespan_ps'],
        scope='independent RWDL service, exact native addresses/commands, physical collection/HB/CDC, finite gateway and SRAM drain; read-only subsystem evidence',
        limits='same physical central machine, different static address views; not a Central+/Distributed application comparison, measured hardware calibration or full physical closure; no WR/PIM')
    write_json(output/'analysis.json',report)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--booksim-binary',type=Path,required=True);p.add_argument('--payload-bytes',type=int,default=256*1024)
    args=p.parse_args();run(args.output,args.booksim_binary,args.payload_bytes)


if __name__=='__main__':main()
