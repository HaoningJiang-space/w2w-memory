#!/usr/bin/env python3
"""Fixed small native memory-island gate, with independent saved-result readback.

No full FFN or placement result is inferred. Outputs must be in a fresh isolated
hn072 workspace. Existing immutable native tools are used on both sides.
"""
import argparse,copy,gzip,hashlib,json,os,platform,random,resource,statistics,subprocess,sys,time
from dataclasses import asdict
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
def read(path):return json.loads(path.read_text())


def worker(out,case,mode,binary):
    from types import SimpleNamespace
    from tools.memory_island_inputs import inputs
    from w2w.backends.ramulator import VerticalRWDL
    from w2w.backends.ramulator.island import NativeMemoryIsland
    from w2w.backends.ramulator.rwdl import RamulatorRWDL
    from w2w.backends.booksim.adapter import factory
    from w2w.backends.booksim.runtime.online_booksim import OnlineBookSim
    from w2w.system.kernel import execute_system
    spec,graph=inputs(case);out.mkdir(exist_ok=False)
    write(out/'input.json',dict(spec=asdict(spec),graph=asdict(graph),max_ps=100000000,
        operand_readiness='contiguous_prefix',compute_contexts=1))
    hashes=hashlib.sha256();counts=dict(mutations=0,progress=0,completed=0)
    request=OnlineBookSim._request
    def observe(self,row):
        if row['command'] in ('submit','supply','commit','boundary'):
            hashes.update(json.dumps(dict(request=row),sort_keys=True,separators=(',',':')).encode()+b'\n');counts['mutations']+=1
        reply=request(self,row)
        for kind in ('progress','completed'):
            for event in reply.get(kind,()):
                hashes.update(json.dumps({kind:event},sort_keys=True,separators=(',',':')).encode()+b'\n');counts[kind]+=1
        return reply
    OnlineBookSim._request=observe
    policy=spec.stack.native_policy
    profile=SimpleNamespace(controller=policy,timing=SimpleNamespace(**{k:v for k,v in vars(policy).items() if k.startswith('n')}))
    backend=RamulatorRWDL(len(spec.stack.memory_regions),domain_count=len(spec.stack.dram_domains),
        array_bytes=spec.stack.dram_domains[0].capacity_bytes,profile=profile,refresh=True,command_trace=out/'commands')
    native=(VerticalRWDL(spec,request_control=True,backend=backend) if mode=='off' else NativeMemoryIsland(spec,backend=backend))
    if mode=='native':native.internal_clock_service=False
    from w2w.system.kernel import SystemExecution
    times=SystemExecution._times;wakes=[]
    def observed(self,*args):
        for at in times(self,*args):wakes.append(at);yield at
    SystemExecution._times=observed
    start=time.perf_counter();cpu=time.process_time()
    try:
        result=execute_system(spec,graph,native=native,time_advance='boundaries',operand_readiness='contiguous_prefix',
            max_ps=100000000,
            network_factory=factory(binary=binary,directory=out/'network'))
    finally:native.close()
    wall=time.perf_counter()-start;cpu=time.process_time()-cpu
    child_cpu=resource.getrusage(resource.RUSAGE_CHILDREN)
    write(out/'wakeups.json',wakes)
    if mode!='off':result['memory_island']=native.coordination_record()
    with gzip.open(out/'result.json.gz','wt',compresslevel=3) as stream:json.dump(result,stream)
    commands=hashlib.sha256()
    for path in sorted(out.glob('commands.ch*')):commands.update(path.name.encode());commands.update(path.read_bytes())
    write(out/'worker.json',dict(complete=True,case=case,mode=mode,
        execution_wall_seconds=wall,python_cpu_seconds=cpu,booksim_child_cpu_seconds=child_cpu.ru_utime+child_cpu.ru_stime,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        kernel_iterations=result['kernel_iterations'],makespan_ps=result['makespan_ps'],drained_ps=result['drained_ps'],
        batched_compute_cycles=result.get('interactive_compute',result.get('compute_epoch',{})).get('batched_compute_cycles',0),
        endpoint_trace_sha256=hashes.hexdigest(),endpoint_trace_counts=counts,commands_sha256=commands.hexdigest(),
        input_sha256=digest(out/'input.json'),result_sha256=digest(out/'result.json.gz'),
        binary_sha256=digest(binary),bridge_sha256=digest(os.environ['W2W_RAMULATOR_BRIDGE']),
        stored_events=len(result['events']),wakeups_sha256=digest(out/'wakeups.json')))


def analyze(root):
    from w2w.validation.vertical_access import audit_vertical_result
    from w2w.validation.request_control import audit_request_control
    from w2w.validation.rwdl_commands import audit_rwdl_commands
    from tools.check_simulator_equivalence import canonical
    start=read(root/'STARTED.json');source=root/'source'
    for name,expected in start['source_hashes'].items():
        if digest(source/name)!=expected:raise ValueError('Changed source: '+name)
    rows=[];groups={}
    for path in sorted(root.glob('run-*')):
        row=read(path/'worker.json');process=read(path/'process.json')
        if (not row['complete'] or process['exit_status'] or row['input_sha256']!=digest(path/'input.json')
                or row['result_sha256']!=digest(path/'result.json.gz')
                or row['binary_sha256']!=start['binary_sha256'] or row['bridge_sha256']!=start['bridge_sha256']):
            raise ValueError('Incomplete or changed worker')
        with gzip.open(path/'result.json.gz','rt') as stream:raw=json.load(stream)
        wakes=read(path/'wakeups.json')
        if row['wakeups_sha256']!=digest(path/'wakeups.json') or len(wakes)!=raw['kernel_iterations'] or wakes!=sorted(set(wakes)):
            raise ValueError('Changed or repeated system wakeup')
        expected_command=['taskset','-c','18,19',start['executable'],str(source.resolve()/'tools/run_memory_island_gate.py'),
            str(path),'--binary',start['binary'],'--worker',row['mode'],'--case',row['case']]
        if process['command']!=expected_command or process['wall_seconds']<=0:
            raise ValueError('Worker process identity differs')
        result=raw
        audit_vertical_result(result);audit_request_control(result);audit_rwdl_commands(result,path/'commands')
        if result['makespan_ps']!=row['makespan_ps'] or result['kernel_iterations']!=row['kernel_iterations']:
            raise ValueError('Worker summary differs from raw result')
        actual_input=read(path/'input.json')
        from tools.memory_island_inputs import inputs
        spec,graph=inputs(row['case'])
        if (actual_input['spec']!=json.loads(json.dumps(asdict(spec)))
                or actual_input['graph']!=json.loads(json.dumps(asdict(graph)))):
            raise ValueError('Worker changes physical inputs')
        commands=hashlib.sha256()
        for file in sorted(path.glob('commands.ch*')):commands.update(file.name.encode());commands.update(file.read_bytes())
        if commands.hexdigest()!=row['commands_sha256']:raise ValueError('Changed native command evidence')
        semantic=canonical(result);semantic.pop('kernel_iterations');semantic.pop('memory_island',None)
        groups.setdefault(row['case'],[]).append((semantic,row))
        rows.append(dict(row,worker_wall_seconds=process['wall_seconds']))
    expected={(case,rep,mode) for case in ('continuous','pressure','inserted')
        for rep in range(3) for mode in ('off','native','coordinated')}
    identities={(read(p/'worker.json')['case'],read(p/'process.json')['repetition'],read(p/'worker.json')['mode']) for p in root.glob('run-*')}
    if identities!=expected or len(rows)!=len(expected):raise ValueError('Missing or repeated worker identity')
    checks=[]
    for case,items in groups.items():
        baseline=next((value,row) for value,row in items if row['mode']=='off')
        for value,row in items:
            if value!=baseline[0]:raise ValueError('Physical record differs: '+case+' '+row['mode'])
            for key in ('endpoint_trace_sha256','endpoint_trace_counts','commands_sha256','input_sha256'):
                if row[key]!=baseline[1][key]:raise ValueError('Native/input trace differs: '+key)
        checks.append(dict(case=case,physical_record_equal=True,native_commands_equal=True,endpoint_trace_equal=True,
            makespan_ps=baseline[1]['makespan_ps'],drained_ps=baseline[1]['drained_ps'],
            iterations={mode:next(row['kernel_iterations'] for _,row in items if row['mode']==mode) for mode in ('off','native','coordinated')},
            host_reduction=1-next(row['kernel_iterations'] for _,row in items if row['mode']=='coordinated')/baseline[1]['kernel_iterations']))
    costs={mode:dict(worker_wall_seconds_median=statistics.median(row['worker_wall_seconds'] for row in rows if row['case']=='continuous' and row['mode']==mode),
        execution_seconds_median=statistics.median(row['execution_wall_seconds'] for row in rows if row['case']=='continuous' and row['mode']==mode),
        booksim_child_cpu_seconds_median=statistics.median(row['booksim_child_cpu_seconds'] for row in rows if row['case']=='continuous' and row['mode']==mode),
        python_cpu_seconds_median=statistics.median(row['python_cpu_seconds'] for row in rows if row['case']=='continuous' and row['mode']==mode),
        peak_rss_kib_median=statistics.median(row['peak_rss_kib'] for row in rows if row['case']=='continuous' and row['mode']==mode),
        stored_events=next(row['stored_events'] for row in rows if row['case']=='continuous' and row['mode']==mode)) for mode in ('off','native','coordinated')}
    verified=dict(passed=True,cases=checks,costs=costs,workers=len(rows),scope='fixed small native system cases; no FFN/placement speedup claim')
    if (root/'VERIFIED.json').exists():
        if read(root/'VERIFIED.json')!=verified:raise ValueError('Saved verification differs from independent readback')
        manifest=read(root/'COMPLETE.json')
        for name,expected in manifest['artifacts'].items():
            if digest(root/name)!=expected:raise ValueError('Changed saved artifact: '+name)
        if manifest['verified_sha256']!=digest(root/'VERIFIED.json'):raise ValueError('Changed verification receipt')
        print('Independent native memory-island readback passed',flush=True)
        return
    write(root/'VERIFIED.json',verified)
    write(root/'COMPLETE.json',dict(complete=True,source_commit=start['source_commit'],artifacts={str(p.relative_to(root)):digest(p) for p in sorted(root.glob('run-*/*')) if p.is_file()},verified_sha256=digest(root/'VERIFIED.json')))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('--binary',type=Path);parser.add_argument('--worker',choices=('off','native','coordinated'))
    parser.add_argument('--case',choices=('continuous','pressure','inserted'));parser.add_argument('--readback',action='store_true')
    args=parser.parse_args();out=args.output.resolve()
    if platform.node()!='ee4e072' or not out.is_relative_to('/Projects/haoning'):
        raise ValueError('Run on the registered hn072 experiment server')
    if args.readback:analyze(out);return
    if args.worker:worker(out,args.case,args.worker,args.binary);return
    if out.exists() or subprocess.check_output(['git','status','--porcelain'],cwd=REPO):raise ValueError('Fresh output and clean committed source required')
    out.mkdir();files=subprocess.check_output(['git','ls-files','w2w','tools/run_memory_island_gate.py','tests/test_memory_island.py','tools/memory_island_inputs.py'],cwd=REPO,text=True).splitlines()
    write(out/'STARTED.json',dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        source_hashes={f:digest(REPO/f) for f in files},host=platform.node(),python=sys.version,executable=sys.executable,
        executable_sha256=digest(Path(sys.executable).resolve()),binary=str(args.binary),binary_sha256=digest(args.binary),
        bridge=os.environ['W2W_RAMULATOR_BRIDGE'],bridge_sha256=digest(os.environ['W2W_RAMULATOR_BRIDGE'])))
    # Source is supplied independently; readback never imports a frozen legacy kernel.
    (out/'source').symlink_to(REPO,target_is_directory=True)
    cells=[(case,rep,mode) for case in ('continuous','pressure','inserted')
        for rep in range(3) for mode in ('off','native','coordinated')]
    random.Random(20261010).shuffle(cells)
    for case,rep,mode in cells:
        directory=out/f'run-{case}-{rep}-{mode}'
        command=['taskset','-c','18,19',sys.executable,str(Path(__file__).resolve()),str(directory),
            '--binary',str(args.binary),'--worker',mode,'--case',case]
        before=time.perf_counter()
        child=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        elapsed=time.perf_counter()-before
        if not directory.exists():directory.mkdir()
        (directory/'worker.log').write_bytes(child.stdout)
        write(directory/'process.json',dict(command=command,exit_status=child.returncode,wall_seconds=elapsed,repetition=rep))
        if child.returncode:raise RuntimeError('Worker failed; preserved: '+str(directory))
        print(case,rep,mode,round(elapsed,4),flush=True)
    analyze(out)


if __name__=='__main__':main()
