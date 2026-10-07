"""Remote single-slice RTL -> Liberty mapping -> pre-layout STA (no P&R)."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(argv, folder, log, env=None, expect_failure=None):
    with log.open('w') as stream:
        proc = subprocess.run([str(v) for v in argv], cwd=folder, env=env,
                              stdout=stream, stderr=subprocess.STDOUT)
    text = log.read_text(errors='replace')
    if expect_failure:
        if proc.returncode == 0 or expect_failure not in text:
            raise AssertionError(f'Negative checker failed: {log}')
    elif proc.returncode:
        raise RuntimeError(f'{argv[0]} exit {proc.returncode}: {log}')
    return text


def replay(executable, records, traces, out, prefix, period):
    results = []
    for record in records:
        name = f'{record["pattern"]}_dir{record["direction"]}'
        args = [*executable, f'+DIR={record["direction"]}', f'+PERIOD_NS={period}',
                f'+WORDS={traces/name/"words.txt"}', f'+CONTROLS={traces/name/"controls.txt"}']
        log = command(args, out, out/f'{prefix}_{name}.log')
        line = next((s for s in log.splitlines() if s.startswith('RESULT ')), None)
        if line is None:
            raise AssertionError(f'No terminal scoreboard result: {prefix}/{name}')
        values = list(map(int, line.split()[1:]))
        expected = [record['accepted'], *record['received'], *record['measured_received'],
                    record['measured_accepted'], record['source_stall_cycles'],
                    record['hb_stall_port_cycles'], record['rx_stall_port_cycles']]
        if values[1:12] != expected:
            raise AssertionError(f'Archived service mismatch: {prefix}/{name}')
        if prefix != 'mapped' and values[12] != record['maximum_pending_payload_bits']:
            raise AssertionError(f'Archived occupancy mismatch: {prefix}/{name}')
        results.append(dict(case=name, result=values))
    return results


def mapped_wrapper():
    # Verification-only star: identical mapped RX cells for both source variants.
    ports = '''input wire clk,rst,cfg_shared_direction,
    input wire native_valid,native_role,native_shared_direction,
    input wire [255:0] native_data, output wire native_ready,
    input wire [2:0] sink_ready, output wire [2:0] sink_valid,
    output wire [767:0] sink_data, output wire [2:0] hb_valid,hb_ready,
    output wire [767:0] hb_data, output wire [11:0] hb_units'''
    text = '`timescale 1ns/1ps\n'
    for variant in ('dup','cfg'):
        text += f'''module endpoint_ppa_{variant} ({ports});
    wire [255:0] hd;
    wire [159:0] ld,rd;
    mapped_tx_{variant} source (
      .clk(clk),.rst(rst),.cfg_shared_direction(cfg_shared_direction),
      .native_valid(native_valid),.native_role(native_role),
      .native_shared_direction(native_shared_direction),.native_data(native_data),
      .native_ready(native_ready),.hb_valid(hb_valid),.hb_ready(hb_ready),
      .home_data(hd),.left_data(ld),.right_data(rd),
      .home_units(hb_units[3:0]),.left_units(hb_units[7:4]),.right_units(hb_units[11:8]));
    assign hb_data={{96'b0,rd,96'b0,ld,hd}};
'''
        for index, (kind, data) in enumerate((('home','hd'),('shared','ld'),('shared','rd'))):
            text += f'''    mapped_rx_{kind} rx{index} (.clk(clk),.rst(rst),
      .beat_valid(hb_valid[{index}]),.beat_ready(hb_ready[{index}]),
      .beat_data({data}),.beat_units(hb_units[{4*index}+:4]),
      .word_valid(sink_valid[{index}]),.word_ready(sink_ready[{index}]),
      .word_data(sink_data[{256*index}+:256]));
'''
        text += 'endmodule\n'
    return text


def run(args):
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    traces=args.traces.resolve();lib=args.liberty.resolve()
    rtl=[ROOT/'rtl/cse_bank.sv',ROOT/'rtl/endpoint_link.sv']
    tb=ROOT/'rtl/endpoint_roundtrip_tb.sv'
    reference=ROOT/'artifacts/results/endpoint/endpoint_roundtrip.json.gz'
    with gzip.open(reference,'rt') as stream:
        records=[r for r in json.load(stream)['records'] if r['width']==160]
    for r in records:
        case=traces/f'{r["pattern"]}_dir{r["direction"]}'
        for name in ('words','controls'):
            if sha(case/f'{name}.txt')!=r[f'{name}_sha256']:
                raise AssertionError(f'Trace changed: {case}/{name}')
    stamp=ROOT/'SOURCE_COMMIT'
    manifest=dict(source_revision=stamp.read_text().strip() if stamp.exists() else
                  subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  library_path=str(lib),library_sha256=sha(lib),period_ns=args.period,
                  started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                  boundary='Pre-layout Nangate45 Liberty mapping and STA; no wire RC, CTS, P&R or power claim',
                  input_sha256={str(p.relative_to(ROOT)):sha(p) for p in
                    [*rtl,tb,reference,ROOT/'rtl/asic/slice_sta.tcl',Path(__file__)]},
                  tools={},simulation={},blocks={})
    def save():
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for tool,flag in (('verilator','--version'),('yosys','-V'),('sta','-version'),('iverilog','-V')):
        manifest['tools'][tool]=command([tool,flag],out,out/f'{tool}_version.log').strip()
    save()
    for configurable in (0,1):
        log=command(['verilator','--lint-only','--timing','-Wall','-Wno-fatal',
                     '--top-module','endpoint_star',f'-GCONFIGURABLE={configurable}',*rtl],
                    out,out/f'lint_cfg{configurable}.log')
        # Keep all warnings, but distinguish real structural errors from width/style notes.
        ids=Counter(re.findall(r'%Warning-([A-Z0-9_]+)',log))
        manifest.setdefault('lint',{})[str(configurable)]=dict(ids)
        if set(ids)&{'LATCH','MULTIDRIVEN','UNOPTFLAT','UNDRIVEN'}:
            raise AssertionError(f'Structural lint warning: {out}/lint_cfg{configurable}.log')
    print('LINT_COMPLETE',flush=True)
    command(['verilator','--binary','--timing','--assert','-Wno-fatal','-j','2',
             '--top-module','endpoint_roundtrip_tb','--Mdir',out/'obj',*rtl,tb],
            out,out/'verilator_build.log')
    manifest['simulation']['verilator']=replay([out/'obj/Vendpoint_roundtrip_tb'],records,traces,out,'verilator',args.period)
    command(['iverilog','-g2012','-s','endpoint_roundtrip_tb','-o',out/'rtl.vvp',*rtl,tb],
            out,out/'iverilog_compile.log')
    manifest['simulation']['iverilog']=replay(['vvp',out/'rtl.vvp'],records,traces,out,'iverilog',args.period)
    if manifest['simulation']['verilator']!=manifest['simulation']['iverilog']:
        raise AssertionError('Simulator cycle/counter mismatch')
    for fault,message in ((1,'Static direction changed'),(2,'Bit-perfect/tag failure')):
        case=traces/'mixed_dir0'
        command([out/'obj/Vendpoint_roundtrip_tb','+DIR=0',f'+FAULT={fault}',
                 f'+WORDS={case/"words.txt"}',f'+CONTROLS={case/"controls.txt"}'],
                out,out/f'negative_{fault}.log',expect_failure=message)
    manifest['negative_checkers_passed']=2
    save();print('RTL_VERIFIED',len(records),'paired cases on each simulator',flush=True)
    (out/'abc.constr').write_text('set_driving_cell BUF_X1\nset_load 5.0\n')
    for name in ('tx_dup','tx_cfg','rx_home','rx_shared'):
        d=out/name;d.mkdir(exist_ok=True)
        tx=name.startswith('tx_');top='endpoint_source' if tx else 'endpoint_rx'
        parameters=f'-set WIDTH 160 -set DEPTH 2 -set CONFIGURABLE {int(name=="tx_cfg")}' if tx else f'-set WIDTH {256 if name=="rx_home" else 160}'
        target='mapped_'+name
        script=f'''read_verilog -sv -DSYNTHESIS {rtl[0]} {rtl[1]}
chparam {parameters} {top}
synth -top {top} -flatten -noabc
dfflibmap -liberty {lib}
abc -liberty {lib} -constr {out/'abc.constr'} -D {args.period*1000:g}
clean
read_liberty -lib {lib}
check -assert
rename {top} {target}
tee -o {d/'stat.json'} stat -json -liberty {lib} {target}
select {target}
write_verilog -noattr -noexpr -selected {d/'netlist.v'}
select *
write_json {d/'netlist.json'}
'''
        (d/'synth.ys').write_text(script)
        print('SYNTHESIZE',name,flush=True)
        command(['yosys','-s',d/'synth.ys'],d,d/'synth.log')
        mapped=json.loads((d/'netlist.json').read_text())['modules'][target]
        cells=Counter(c['type'] for c in mapped['cells'].values() if c['type']!='$scopeinfo')
        if any(c.startswith('$') for c in cells):raise AssertionError(f'Unmapped cells: {name}')
        manifest['blocks'][name]=dict(cells=dict(cells),netlist_sha256=sha(d/'netlist.v'),
                                    sequential_cells=sum(v for c,v in cells.items() if c.startswith(('DFF','SDFF'))))
        env=dict(os.environ,W2W_LIBERTY=str(lib),W2W_NETLIST=str(d/'netlist.v'),
                 W2W_TOP=target,W2W_PERIOD_NS=str(args.period),W2W_TX=str(int(tx)))
        log=command(['sta','-exit',ROOT/'rtl/asic/slice_sta.tcl'],d,d/'sta.log',env)
        if 'STA_COMPLETE' not in log or re.search(r'(^|\n)Error:',log):
            raise AssertionError(f'STA incomplete: {d}/sta.log')
        manifest['blocks'][name]['sta_complete']=True
        save()
    # Generate zero-delay Liberty cell models; no timing simulation claim.
    script=f'read_liberty {lib}\nwrite_verilog -noattr {out/"cells.v"}\n'
    (out/'models.ys').write_text(script)
    command(['yosys','-s',out/'models.ys'],out,out/'models.log')
    (out/'mapped_star.sv').write_text(mapped_wrapper())
    netlists=[out/name/'netlist.v' for name in manifest['blocks']]
    command(['iverilog','-g2012','-DPPA_NETLIST','-s','endpoint_roundtrip_tb',
             '-o',out/'mapped.vvp',out/'cells.v',*netlists,out/'mapped_star.sv',tb],
            out,out/'mapped_compile.log')
    manifest['simulation']['mapped_zero_delay']=replay(['vvp',out/'mapped.vvp'],records,traces,out,'mapped',args.period)
    for a,b in zip(manifest['simulation']['verilator'],manifest['simulation']['mapped_zero_delay']):
        if a['result'][:12]!=b['result'][:12]:
            raise AssertionError('Mapped cycle/scoreboard mismatch')
    manifest['completed_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    save();print('ASIC_PIPELINE_COMPLETE',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--traces',type=Path,required=True)
    p.add_argument('--liberty',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--period',type=float,default=2.0)
    run(p.parse_args())
