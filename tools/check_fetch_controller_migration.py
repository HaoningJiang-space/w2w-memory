#!/usr/bin/env python3
"""Exact finite-fetch migration including command and native endpoint traces."""
import argparse,gzip,hashlib,json,subprocess,sys
from pathlib import Path


def worker(source,out,case,binary):
    sys.path.insert(0,str(source))
    from types import SimpleNamespace
    from tools.run_fetch_factor_probe import inputs
    from w2w.common.fingerprints import digest_read_v1 as digest
    from w2w.backends.ramulator import VerticalRWDL
    from w2w.backends.ramulator.rwdl import RamulatorRWDL
    from w2w.backends.booksim.adapter import factory
    from w2w.backends.booksim.runtime.online_booksim import OnlineBookSim
    from w2w.system.kernel import execute_system
    from w2w.validation.vertical_access import audit_vertical_result
    from w2w.validation.request_control import audit_request_control
    from w2w.validation.rwdl_commands import audit_rwdl_commands
    out.mkdir(exist_ok=False);spec,graph,meta,data=inputs(case)
    trace=hashlib.sha256();counts=dict(mutations=0,progress=0,completed=0);request=OnlineBookSim._request
    def observe(self,row):
        if row['command'] in ('submit','supply','commit','boundary'):
            trace.update(json.dumps(dict(request=row),sort_keys=True,separators=(',',':')).encode()+b'\n');counts['mutations']+=1
        reply=request(self,row)
        for kind in ('progress','completed'):
            for event in reply.get(kind,()):
                trace.update(json.dumps({kind:event},sort_keys=True,separators=(',',':')).encode()+b'\n');counts[kind]+=1
        return reply
    OnlineBookSim._request=observe;policy=spec.stack.native_policy
    profile=SimpleNamespace(controller=policy,timing=SimpleNamespace(**{k:v for k,v in vars(policy).items() if k.startswith('n')}))
    backend=RamulatorRWDL(len(spec.stack.memory_regions),domain_count=len(spec.stack.dram_domains),
        array_bytes=spec.stack.dram_domains[0].capacity_bytes,profile=profile,refresh=True,command_trace=out/'commands')
    native=VerticalRWDL(spec,backend=backend,request_control=True,gateway_trace_bin_ps=100000)
    try:
        r=execute_system(spec,graph,native=native,compute_contexts=2,fetch_contexts=2,read_issue_policy='round_robin',
            operand_readiness='contiguous_prefix',activation_sram_read_bytes_per_cycle=128,time_advance='boundaries',
            max_ps=1000000000,network_factory=factory(binary=binary,directory=out/'network',ready_router_ids=tuple(x.id for x in spec.routers),ready_slots=16))
    finally:native.close()
    audit_vertical_result(r);audit_request_control(r);commands_audit=audit_rwdl_commands(r,out/'commands')
    with gzip.open(out/'result.json.gz','wt',compresslevel=3) as f:json.dump(r,f)
    commands=hashlib.sha256()
    for path in sorted(out.glob('commands.ch*')):commands.update(path.name.encode());commands.update(path.read_bytes())
    proof=dict(complete=True,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),
        input_sha256=digest(data),makespan_ps=r['makespan_ps'],endpoint_trace_sha256=trace.hexdigest(),endpoint_trace_counts=counts,
        commands_sha256=commands.hexdigest(),command_audit=commands_audit)
    (out/'completion.json').write_text(json.dumps(proof,indent=2)+'\n')


def check(root,baseline,candidate,binary,readback=False):
    if not readback:root.mkdir(exist_ok=False)
    elif not root.is_dir():raise ValueError('Trace readback requires an existing archive')
    rows=[];tools=set()
    for case in ('d1-round_robin-hybrid','d1-round_robin-phase-split'):
        for label,source in (() if readback else (('baseline',baseline),('candidate',candidate))):
            out=root/(case+'-'+label)
            with (root/(case+'-'+label+'.log')).open('xb') as log:
                subprocess.run([sys.executable,__file__,'--worker','--source',str(source),'--output',str(out),
                    '--case',case,'--booksim-binary',str(binary)],stdout=log,stderr=subprocess.STDOUT,check=True)
        a=root/(case+'-baseline');b=root/(case+'-candidate')
        subprocess.run([sys.executable,str(Path(__file__).with_name('check_simulator_equivalence.py')),'--baseline',str(a),'--candidate',str(b),
            '--output',str(root/(case+'-physical-equivalence.json'))],cwd=candidate,check=True)
        old=json.loads((a/'completion.json').read_text());new=json.loads((b/'completion.json').read_text())
        from w2w.validation.rwdl_commands import audit_rwdl_commands
        from w2w.common.fingerprints import digest_read_v1 as digest
        identities=[]
        for directory,source,proof in ((a,baseline,old),(b,candidate,new)):
            if not proof['complete'] or proof['source_commit']!=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip():
                raise ValueError('Saved trace source identity differs')
            with gzip.open(directory/'result.json.gz','rt') as f:r=json.load(f)
            if r['makespan_ps']!=proof['makespan_ps'] or audit_rwdl_commands(r,directory/'commands')!=proof['command_audit']:
                raise ValueError('Saved command audit differs')
            command_files=sorted(directory.glob('commands.ch*'));command_hash=hashlib.sha256()
            if not command_files:raise ValueError('Missing native command capture')
            for path in command_files:command_hash.update(path.name.encode());command_hash.update(path.read_bytes())
            if command_hash.hexdigest()!=proof['commands_sha256']:raise ValueError('Saved native command bytes changed')
            tools.add((r['network']['identity']['binary_sha256'],r['native']['bridge_sha256']))
            identities.append(dict(raw_sha256=hashlib.sha256((directory/'result.json.gz').read_bytes()).hexdigest(),
                graph_sha256=digest(r['graph']),stack_sha256=digest(r['spec']['stack'])))
        if identities[0]['graph_sha256']!=identities[1]['graph_sha256'] or identities[0]['stack_sha256']!=identities[1]['stack_sha256']:
            raise ValueError('Trace migration changed machine or graph')
        for key in ('input_sha256','makespan_ps','endpoint_trace_sha256','endpoint_trace_counts','commands_sha256','command_audit'):
            if old[key]!=new[key]:raise ValueError('Finite-fetch trace migration changed '+key)
        rows.append(dict(case=case,passed=True,baseline_source=old['source_commit'],candidate_source=new['source_commit'],
            makespan_ps=new['makespan_ps'],commands_sha256=new['commands_sha256'],endpoint_trace_sha256=new['endpoint_trace_sha256'],
            endpoint_trace_counts=new['endpoint_trace_counts'],command_audit=new['command_audit'],capture_identities=identities))
    if len(tools)!=1:raise ValueError('Trace migration changed native tools')
    proof=dict(passed=True,cases=rows,native_tools=list(next(iter(tools))),
        analysis_source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=Path(__file__).resolve().parents[1],text=True).strip(),
        contract='Same frozen native tools and inputs; full physical record, integer ps, ACT/PRE/RD/REF '
        'time/address logs and native submit/supply/commit/progress/completion trace fingerprints match. No architecture speedup claimed.')
    (root/'analysis.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worker',action='store_true');p.add_argument('--source',type=Path);p.add_argument('--case')
    p.add_argument('--readback',action='store_true',help='Audit existing complete captures without running simulation')
    p.add_argument('--baseline-source',type=Path);p.add_argument('--candidate-source',type=Path)
    p.add_argument('--booksim-binary',type=Path,required=True);a=p.parse_args()
    if a.worker:worker(a.source,a.output,a.case,a.booksim_binary)
    else:
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        check(a.output,a.baseline_source,a.candidate_source,a.booksim_binary,a.readback)


if __name__=='__main__':main()
