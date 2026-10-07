"""Payload RTL, generic synthesis and unchanged wafer service for shared egress."""
import argparse
from collections import Counter, deque
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path
import random
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


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--tools',default='memory_results/cse_tools')
    args=parser.parse_args()
    run(args.output,args.tools)
