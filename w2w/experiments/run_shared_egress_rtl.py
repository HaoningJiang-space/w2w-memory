"""Payload RTL, generic synthesis and unchanged wafer service for shared egress."""
import argparse
from collections import Counter, deque
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path
import random
from math import gcd
import subprocess
import time
import numpy as np
from w2w.domain import EndpointSpec
from w2w.endpoints.role_execution import execute_periodic, ratio_sequence
from w2w.provenance import provenance
from w2w.service.cost import CostModel
from w2w.service.evaluator import CandidateEvaluator
from w2w.service.guaranteed_service_exchange import contoured_geometry
from w2w.synthesis.role_interfaces import make_candidate, static_shared_fifo


def command(args, log):
    result = subprocess.run([str(v) for v in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    Path(log).write_text(result.stdout)
    if result.returncode:
        raise RuntimeError(f'Command failed: {args[0]}; see {log}\n{result.stdout[-3000:]}')
    return result.stdout


def vectors(path, width, depth, mode, direction, pattern):
    """Independent FIFO-of-32-bit-tokens oracle, including payload and drain."""
    peer = direction + 1
    fraction = Fraction(256, 256+width)
    sequence = ((0,) if pattern == 'home' else (peer,) if pattern == 'shared' else
                ratio_sequence(0, peer, fraction.numerator, fraction.denominator))
    patterns = ('home', 'shared', 'mixed', 'bursty', 'stalls', 'reject')
    rng = random.Random(840100 + width*100 + direction*10 + patterns.index(pattern))
    # Close both the byte phase (divisor of 8 slots) and 3/13-word source period.
    window = 64*fraction.denominator
    cycles = 2*window if pattern in patterns[:3] else 512
    queues = [deque() for _ in range(3)]
    cursor = issued = 0
    total = [0, 0, 0]
    accepted = [hashlib.sha256() for _ in range(3)]
    delivered = [hashlib.sha256() for _ in range(3)]
    widths = (256, width, width)
    depths = (1, depth, depth)
    before = None
    data = rng.getrandbits(256)
    rows = []
    for tick in range(cycles+64):
        draining = tick >= cycles
        dest = sequence[cursor]
        if pattern == 'reject' and tick % 3 == 0:
            dest = 2-direction
        valid = not draining
        if pattern == 'bursty':
            valid = valid and tick % 8 < 4
        if pattern == 'stalls':
            valid = valid and rng.random() < .8
        ready_mask = 7 if pattern != 'stalls' or draining else sum((rng.random() < .65) << p for p in range(3))
        legal = mode == 0 or dest in (0, peer)
        ready = legal and len(queues[dest]) < depths[dest]
        payload = data
        if valid and ready:
            queues[dest].append(deque((payload >> (32*i)) & 0xffffffff for i in range(8)))
            accepted[dest].update(payload.to_bytes(32,'little'))
            issued += 1
            cursor = (cursor+1) % len(sequence)
            data = rng.getrandbits(256)
        counts, beats = [], []
        for p in range(3):
            tokens = []
            budget = widths[p]//32 if ready_mask & (1 << p) else 0
            while budget and queues[p]:
                tokens.append(queues[p][0].popleft())
                budget -= 1
                if not queues[p][0]:
                    queues[p].popleft()
            counts.append(len(tokens))
            beats.append(sum(value << (32*i) for i, value in enumerate(tokens)))
            total[p] += len(tokens)
            for token in tokens:
                delivered[p].update(token.to_bytes(4,'little'))
            assert len(queues[p]) <= depths[p]
        assert issued*8 == sum(total) + sum(len(word) for q in queues for word in q)
        rows.append(f'{int(valid)} {dest} {payload:064x} {ready_mask:03b} {int(ready)} ' +
                    ' '.join(f'{n} {beat:064x}' for n, beat in zip(counts,beats)))
        if tick == window-1:
            before = total.copy()
        if tick == 2*window-1:
            measured = [(n-old)/8/window for n, old in zip(total,before)]
    assert not any(queues)
    assert [v.hexdigest() for v in accepted] == [v.hexdigest() for v in delivered]
    path.write_text('\n'.join(rows)+'\n')
    result = dict(pattern=pattern, direction=direction, cycles=len(rows), accepted_words=issued,
                  output_token_count=total, payload_sha256=[v.hexdigest() for v in delivered],
                  vectors_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    if pattern in patterns[:3]:
        spec = EndpointSpec(widths,depths,shared_fifo_ports=(1,2) if mode else (),shared_serializer=mode==2)
        period = execute_periodic(spec,sequence,selected_shared_port=peer if mode else None)
        assert np.allclose(measured,period['rate_per_native'],atol=1e-12,rtol=0)
        result.update(measured_rates=measured,periodic_rates=period['rate_per_native'])
    return result


def run(output, tools_dir):
    if subprocess.check_output(['git','status','--porcelain'],text=True).strip():
        raise RuntimeError('Commit source before RTL experiment')
    started = time.monotonic()
    out = Path(output).resolve()
    out.mkdir(parents=True,exist_ok=True)
    tools = Path(tools_dir).resolve()/'bin'
    yosys, iverilog, vvp = (tools/name for name in ('yosys','iverilog','vvp'))
    versions = dict(yosys=command([yosys,'-V'],out/'yosys_version.log').strip(),
                    iverilog=command([iverilog,'-V'],out/'iverilog_version.log').splitlines()[0])
    source = Path('rtl/cse_bank.sv').resolve()
    bench = Path('rtl/cse_tb.sv').resolve()
    hardware = []
    for width, depth in ((128,1),(160,2)):
        for mode in range(3):
            name = f'w{width}_d{depth}_m{mode}'
            folder = out/name
            folder.mkdir(exist_ok=True)
            script = (f'read_verilog -sv {source}; '
                      f'chparam -set SHARED_WIDTH {width} -set SHARED_DEPTH {depth} -set MODE {mode} cse_bank; '
                      'synth -top cse_bank -flatten -noabc; abc -g simple; clean; check -assert; '
                      f'tee -o {folder}/stat.json stat -json; write_json {folder}/netlist.json; '
                      f'write_verilog -noattr {folder}/netlist.v')
            (folder/'synth.ys').write_text(script+'\n')
            command([yosys,'-s',folder/'synth.ys'],folder/'synth.log')
            netlist = json.loads((folder/'netlist.json').read_text())
            cells = Counter(c['type'] for c in netlist['modules']['cse_bank']['cells'].values()
                            if c['type'] != '$scopeinfo')
            assert not any('LATCH' in c.upper() or 'MEM' in c.upper() for c in cells)
            flops = sum(n for c,n in cells.items() if 'DFF' in c)
            sims = []
            for gate in (False,True):
                exe = folder/('gate.vvp' if gate else 'rtl.vvp')
                args = [iverilog,'-g2012','-s','cse_tb','-P',f'cse_tb.SHARED_WIDTH={width}',
                        '-P',f'cse_tb.SHARED_DEPTH={depth}','-P',f'cse_tb.MODE={mode}','-o',exe]
                if gate:
                    args.append('-DGATE')
                args.extend((bench,folder/'netlist.v' if gate else source))
                command(args,folder/('compile_gate.log' if gate else 'compile_rtl.log'))
                for direction in (0,1):
                    for pattern in ('home','shared','mixed','bursty','stalls','reject'):
                        stem = f'{pattern}_dir{direction}'
                        stimulus = folder/(stem+'.vec')
                        evidence = vectors(stimulus,width,depth,mode,direction,pattern)
                        log = folder/(stem+('_gate.log' if gate else '_rtl.log'))
                        response = command([vvp,exe,f'+STIM={stimulus}',f'+DIR={direction}'],log)
                        assert f'PASS {evidence["cycles"]} cycles' in response
                        sims.append(dict(level='mapped_generic' if gate else 'rtl',**evidence))
            payload_bits = 256*(1+(2 if mode==0 else 1)*depth)
            assert flops >= payload_bits
            hardware.append(dict(id=name,width=width,depth=depth,mode=mode,cells=dict(cells),
                flip_flops=flops,payload_register_bits=payload_bits,control_flip_flops=flops-payload_bits,
                combinational_cells=sum(cells.values())-flops,total_cells=sum(cells.values()),
                netlist_sha256=hashlib.sha256((folder/'netlist.json').read_bytes()).hexdigest(),simulations=sims))
            print('HARDWARE',name,'FF',flops,'comb',sum(cells.values())-flops,'simulations',len(sims),flush=True)
    old_service=json.loads(gzip.decompress(Path('artifacts/results/endpoint/static_shared_fifo.json.gz').read_bytes()))
    competition=json.loads(gzip.decompress(Path('artifacts/results/endpoint/architecture_competition.json.gz').read_bytes()))
    previous={r['id']:r for r in old_service['designs']}
    source_rows={r['id']:r for r in competition['search']['catalog']}
    physical=contoured_geometry()
    wafer=[]
    for width in (128,160):
        depth=1 if width==128 else 2
        name=f'k3_23_random9_maxweight_h256s{width}_d1{depth}_buffered'
        row=source_rows[name]
        spec=EndpointSpec(**{k:v for k,v in row['endpoint'].items() if k!='native'})
        old=make_candidate(physical,row['pairs'],name,'k3',spec,Fraction(row['home_fraction']))
        pooled=static_shared_fifo(old)
        shared=static_shared_fifo(old,share_serializer=True)
        evaluator=CandidateEvaluator(shared)
        replays={key:evaluator.replay(active) for key,active in old_service['scenarios'].items()}
        reference=previous[name+'_static_fifo']
        error=max(abs(replays[key]['executed_tb_s']-reference['replays'][key]['executed_tb_s']) for key in replays)
        for key in replays:
            assert np.allclose(replays[key]['served_tb_s'],reference['replays'][key]['served_tb_s'],atol=1e-12,rtol=0)
            assert abs(replays[key]['common_tb_s']-reference['replays'][key]['common_tb_s'])<1e-12
        population=evaluator.population(9)
        assert shared.layout.sha256==reference['layout_hash']
        assert abs(population['exact_mean_tb_s']-reference['scores']['random9'])<1e-12
        costs=[CostModel.evaluate(d) for d in (old,pooled,shared)]
        for key in ('export_lane_bits','access_wire_bit_mm','pipeline_register_bits','bank_access_driver_bits',
                    'bank_port_connections','configured_hb_signal_bits'):
            assert len({c[key] for c in costs})==1
        assert costs[1]['endpoint_storage_bits']==costs[2]['endpoint_storage_bits']
        assert costs[1]['serializer_instances']==2*costs[2]['serializer_instances']
        wafer.append(dict(width=width,depth=depth,id=shared.name,endpoint=shared.endpoint.record(),
            layout_hash=shared.layout.sha256,shared_directions=shared.shared_directions,costs=costs,
            replays=replays,population=population,service_error=error,composition=evaluator.composition))
    inputs=[source,bench,Path('docs/methods/SHARED_EGRESS_RTL.md'),
            Path('artifacts/results/endpoint/static_shared_fifo.json.gz'),
            Path('artifacts/results/endpoint/architecture_competition.json.gz')]
    result=dict(provenance=provenance(),tools=versions,hardware=hardware,wafer=wafer,
        input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        scope='Synthesizable registered FIFO + 32-bit-lane packetizer; generic gates only, no library/STA/routing/power',
        verification=dict(hardware_designs=len(hardware),simulation_runs=sum(len(r['simulations']) for r in hardware),
            checked_cycles=sum(s['cycles'] for r in hardware for s in r['simulations']),
            max_service_error=max(r['service_error'] for r in wafer),
            lp_solves=sum(p['lp_solves'] for r in wafer for p in r['replays'].values()),
            max_resource_residual=max(max(p['witness_residual'],p['lp_residual']) for r in wafer for p in r['replays'].values())),
        elapsed_seconds=time.monotonic()-started)
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('VERIFIED',result['verification'],'seconds',result['elapsed_seconds'],flush=True)


def roundtrip_trace(folder, width, pattern, direction):
    """Stimulus only: tagged random words and external offer/receiver schedules."""
    fraction = Fraction(256, 256+width)
    sequence = ((0,) if pattern == 'home' else (1,) if pattern in ('shared', 'tail') else
                ratio_sequence(0, 1, fraction.numerator, fraction.denominator))
    count = 17 if pattern == 'tail' else 10400
    rng = random.Random(9700 + width + ('home','shared','mixed','bursty','stalls','long_stall','tail').index(pattern))
    words = folder/'words.txt'
    controls = folder/'controls.txt'
    # Tag occupies payload bits in this synthetic trace, not an unpriced tag bus.
    words.write_text(''.join(f'{sequence[i % len(sequence)]} {(rng.getrandbits(224)<<32)|i:064x}\n'
                             for i in range(count)))
    rows=[]
    for tick in range(60000):
        offer, ready = 1, 7
        if pattern == 'bursty':
            offer=int(tick % 16 < 8)
        elif pattern == 'stalls':
            offer=int(rng.random()<.8)
            ready=sum(int(rng.random()<.65)<<p for p in range(3))
        elif pattern == 'long_stall':
            if tick % 1000 < 400:
                ready &= ~(1 << (direction+1))
            if 500 <= tick % 1000 < 550:
                ready &= ~1
        rows.append(f'{offer} {ready}\n')
    controls.write_text(''.join(rows))
    return dict(words=count,sequence=sequence,words_sha256=hashlib.sha256(words.read_bytes()).hexdigest(),
                controls_sha256=hashlib.sha256(controls.read_bytes()).hexdigest())


def roundtrip_storage(width, depth, configurable):
    """Declared payload state, including held beats and both physical receivers.

    This is not a synthesis cell count. Control widths are separately counted;
    no projected wire or receiver savings from pooling the transmitter.
    """
    shared = 1 if configurable else 2
    fifo = 256*(1+shared*depth)
    beats = 256+shared*width
    rx = 256+2*(256+width-gcd(256,width))
    fifo_control = 1+shared*(1 if depth==1 else 2)
    phase = shared*(0 if width==256 else 1 if width==128 else 3)
    beat_control = (1+shared)*5  # four valid-unit bits and valid bit per beat
    rx_control = (8).bit_length()+2*((256+width-gcd(256,width))//32).bit_length()
    return dict(tx_fifo_payload_bits=fifo,tx_beat_payload_bits=beats,rx_payload_bits=rx,
                total_payload_bits=fifo+beats+rx,tx_control_bits=fifo_control+phase+beat_control,
                rx_control_bits=rx_control,data_lane_bits=256+2*width,
                hb_valid_units_bits=15,hb_ready_bits=3,
                config_scope='One external frozen direction input; no trace sequencer or reorder RAM',
                scope='Single source slice plus three physical receivers; declared registers, not mapped area')


def run_roundtrip(output, tools_dir):
    if subprocess.check_output(['git','status','--porcelain'],text=True).strip():
        raise RuntimeError('Commit source before endpoint roundtrip experiment')
    started=time.monotonic()
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    tools=Path(tools_dir).resolve()/'bin'
    # Extract the physical star from the existing geometry, without solving a wafer LP.
    physical=contoured_geometry()
    for m in range(len(physical.memory)):
        edges=[next((dict(e) for e in physical.edges if e['m']==m and e['mp']==p),None) for p in (0,2,3)]
        if all(e is not None for e in edges) and len({e['c'] for e in edges})==3:
            break
    else:
        raise AssertionError('No legal three-destination star in current H/plus')
    for e in edges:
        cr=physical.compute[e['c']].vertical_connectors[e['cp']]
        mr=physical.memory[e['m']].vertical_connectors[e['mp']]
        area=physical.region(cr).intersection(physical.region(mr)).area
        assert area>0 and abs(area-e['overlap_mm2'])<1e-10
    sources=[Path(p).resolve() for p in ('rtl/cse_bank.sv','rtl/endpoint_link.sv','rtl/endpoint_roundtrip_tb.sv')]
    versions=dict(iverilog=command([tools/'iverilog','-V'],out/'iverilog_version.log').splitlines()[0])
    records=[]
    pairs=[(160,2),(128,1),(192,1),(192,2),(256,1)]
    for width,depth in pairs:
        folder=out/f'w{width}_d{depth}';folder.mkdir(exist_ok=True)
        exe=folder/'roundtrip.vvp'
        command([tools/'iverilog','-g2012','-s','endpoint_roundtrip_tb',
                 '-P',f'endpoint_roundtrip_tb.WIDTH={width}','-P',f'endpoint_roundtrip_tb.DEPTH={depth}',
                 '-o',exe,*sources],folder/'compile.log')
        patterns=('home','shared','mixed','bursty','stalls','long_stall','tail') if width==160 else ('shared','stalls','tail')
        for direction in ((0,1) if width==160 else (0,)):
            for pattern in patterns:
                case=folder/f'{pattern}_dir{direction}';case.mkdir(exist_ok=True)
                trace=roundtrip_trace(case,width,pattern,direction)
                response=command([tools/'vvp',exe,f'+DIR={direction}',f'+WORDS={case/"words.txt"}',
                                  f'+CONTROLS={case/"controls.txt"}'],case/'run.log')
                line=next(v for v in response.splitlines() if v.startswith('RESULT '))
                values=list(map(int,line.split()[1:]))
                cycles,accepted,*_=values
                assert accepted==trace['words'] and sum(values[2:5])==accepted
                record=dict(width=width,depth=depth,pattern=pattern,direction=direction,**trace,
                    cycles=cycles,accepted=accepted,received=values[2:5],measured_received=values[5:8],
                    measured_accepted=values[8],source_stall_cycles=values[9],hb_stall_port_cycles=values[10],
                    rx_stall_port_cycles=values[11],maximum_pending_payload_bits=values[12],
                    bitperfect=True,cycle_equivalent=True,hold_checked=True,conservation_checked=True)
                if pattern in ('home','shared','mixed'):
                    sequence=tuple(direction+1 if p else 0 for p in trace['sequence'])
                    spec=EndpointSpec((256,width,width),(1,depth,depth))
                    reference=execute_periodic(spec,sequence)
                    actual=np.array(values[5:8])/8320
                    expected=np.array(reference['rate_per_native'])
                    assert np.all(np.abs(actual-expected)<=1/8320+1e-12),(actual,expected)
                    record.update(received_words_per_cycle=actual.tolist(),python_reference=expected.tolist(),
                                  measurement_cycles=8320,boundary_tolerance_words=1)
                if pattern in ('stalls','long_stall'):
                    assert all(values[i]>0 for i in (9,10,11))
                records.append(record)
                print('ROUNDTRIP',width,depth,direction,pattern,'words',accepted,'cycles',cycles,flush=True)
    # Demonstrate two checkers reject their specific deliberately injected fault.
    fault_case=out/'w160_d2'/'tail_dir0'
    faults=[]
    for fault,message in ((1,'Static direction changed'),(2,'Bit-perfect/tag failure')):
        args=[str(tools/'vvp'),str(out/'w160_d2'/'roundtrip.vvp'),'+DIR=0',f'+FAULT={fault}',
              f'+WORDS={fault_case/"words.txt"}',f'+CONTROLS={fault_case/"controls.txt"}']
        r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        (out/f'negative_{fault}.log').write_text(r.stdout)
        assert r.returncode!=0 and message in r.stdout
        faults.append(dict(fault=fault,expected_failure=message,detected=True))
    inputs=sources+[Path('docs/methods/ENDPOINT_ROUNDTRIP.md')]
    result=dict(provenance=provenance(),tools=versions,geometry=dict(memory=m,edges=edges,
        node_aliases={'M0':m,'C0':edges[0]['c'],'C1':edges[1]['c'],'C2':edges[2]['c']},
        source='H/plus physical connector intersections; no C-to-C links'),records=records,negative_checks=faults,
        storage={name:roundtrip_storage(160,2,pooled) for name,pooled in [('duplicated',False),('configurable',True)]},
        input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        verification=dict(paired_traces=len(records),architecture_runs=2*len(records),
            accepted_words_per_architecture=sum(r['accepted'] for r in records),
            paired_cycles=sum(r['cycles'] for r in records),wafer_lp_solves=0,synthesis_runs=0),
        scope='Functional single-source TX/HB/RX star, registered ready/valid, ordered stream per physical edge; no link delay, timing, area or power',
        elapsed_seconds=time.monotonic()-started)
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('VERIFIED',result['verification'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--tools',default='memory_results/cse_tools')
    parser.add_argument('--roundtrip',action='store_true',help='Functional TX/RX star; no synthesis or wafer LP')
    args=parser.parse_args()
    (run_roundtrip if args.roundtrip else run)(args.output,args.tools)
