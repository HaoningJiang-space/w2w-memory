"""Remote single-slice RTL -> Liberty mapping -> pre-layout STA (no P&R)."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
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


def repair_block(folder, target, lib, env):
    """Bounded pre-layout ECO: input delay buffers and same-function upsizing.

    No constraints, RTL, clock paths or sequential cells are changed. These
    repairs have zero wire RC and must not be called physical timing closure.
    """
    initial=folder/'initial';initial.mkdir()
    for name in ('netlist.json','netlist.v','stat.json','sta.log','hold.tsv'):
        shutil.copy2(folder/name,initial/name)
    history=[]
    for iteration in range(9):
        timing=(folder/'hold.tsv').read_text().splitlines()
        metrics={s.split()[1]:float(s.split()[2]) for s in timing if s.startswith('METRIC ')}
        starts=sorted({s.split()[1] for s in timing if s.startswith('HOLD ')})
        electrical=(folder/'sta.log').read_text().split('=== ELECTRICAL ===')[1]
        violations=[line for line in electrical.splitlines() if '(VIOLATED)' in line]
        if violations and ('max slew' in electrical or 'max fanout' in electrical):
            raise AssertionError('ECO supports capacitance only; unexpected electrical violation')
        pins=sorted({line.split()[0] for line in violations})
        if metrics['setup_ns']<0:
            raise AssertionError(f'ECO would leave setup failing: {folder}')
        if not starts and not pins:
            if metrics['hold_ns']<0:raise AssertionError('Negative hold missing from path list')
            return dict(iterations=history,final_slack_ns=metrics,
                        all_hold_paths_nonnegative=True,electrical_violations=0)
        if iteration==8:raise AssertionError(f'ECO pass limit: {folder}')
        design=json.loads((folder/'netlist.json').read_text())
        top=design['modules'][target];cells=top['cells']
        bits=[b for c in cells.values() for bs in c['connections'].values() for b in bs if isinstance(b,int)]
        bits += [b for p in top['ports'].values() for b in p['bits'] if isinstance(b,int)]
        next_bit=max(bits)+1
        changes=dict(round=iteration+1,hold_buffers=[],resized=[])
        for pin in pins:
            instance=pin.rsplit('/',1)[0]
            cell=cells[instance];old=cell['type']
            match=re.fullmatch(r'(.+)_X(1|2|4|8)',old)
            if not match:raise AssertionError(f'No bounded size successor: {old}')
            new=f'{match[1]}_X{2*int(match[2])}'
            if new not in design['modules']:raise AssertionError(f'Library lacks {new}')
            # Nangate X strengths must have exactly the same signal interface.
            if design['modules'][old]['ports']!=design['modules'][new]['ports']:
                raise AssertionError(f'Library port mismatch: {old}/{new}')
            cell['type']=new
            changes['resized'].append(dict(instance=instance,old=old,new=new))
        for start in starts:
            match=re.fullmatch(r'([^\[]+)(?:\[(\d+)\])?',start)
            if not match or match[1] not in top['ports']:
                raise AssertionError(f'Internal hold needs a different repair: {start}')
            port=top['ports'][match[1]]
            if port['direction']!='input' or port.get('upto',0) or match[1] in ('clk','rst'):
                raise AssertionError(f'Unsupported hold startpoint: {start}')
            index=int(match[2] or 0)-port.get('offset',0)
            old_bit=port['bits'][index];new_bit=next_bit;next_bit+=1
            loads=0
            for cell in list(cells.values()):
                for name,connection in cell['connections'].items():
                    if old_bit in connection:
                        if cell['port_directions'][name]!='input':
                            raise AssertionError(f'Input net has internal driver: {start}')
                        loads+=connection.count(old_bit)
                        cell['connections'][name]=[new_bit if b==old_bit else b for b in connection]
            if not loads:raise AssertionError(f'Hold input has no loads: {start}')
            name=f'w2w_hold_{iteration}_{len(changes["hold_buffers"])}'
            if name in cells:raise AssertionError('ECO name collision')
            cells[name]=dict(hide_name=0,type='BUF_X1',parameters={},attributes={},
                             port_directions=dict(A='input',Z='output'),
                             connections=dict(A=[old_bit],Z=[new_bit]))
            top['netnames'][name+'_net']=dict(hide_name=0,bits=[new_bit],attributes={})
            changes['hold_buffers'].append(dict(instance=name,startpoint=start))
        step=folder/f'eco_{iteration+1}';step.mkdir()
        (step/'edited.json').write_text(json.dumps(design))
        (step/'changes.json').write_text(json.dumps(changes,indent=2)+'\n')
        script=f'''read_json {step/'edited.json'}
check -assert
tee -o {folder/'stat.json'} stat -json -liberty {lib} {target}
select {target}
write_verilog -noattr -noexpr -selected {folder/'netlist.v'}
select *
write_json {folder/'netlist.json'}
'''
        (step/'write.ys').write_text(script)
        command(['yosys','-s',step/'write.ys'],step,step/'write.log')
        log=command(['sta','-exit',ROOT/'rtl/asic/slice_sta.tcl'],folder,folder/'sta.log',env)
        if 'STA_COMPLETE' not in log or re.search(r'(^|\n)Error:',log):
            raise AssertionError(f'ECO STA incomplete: {folder}')
        for name in ('stat.json','sta.log','hold.tsv'):
            shutil.copy2(folder/name,step/name)
        history.append(changes)
        print('ECO',target,iteration+1,'buffers',len(changes['hold_buffers']),
              'resizes',len(changes['resized']),flush=True)


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
                  repair_requested=args.repair,
                  physical_requested=bool(args.openroad),
                  input_sha256={str(p.relative_to(ROOT)):sha(p) for p in
                    [*rtl,tb,reference,ROOT/'rtl/asic/slice_sta.tcl',
                     ROOT/'rtl/asic/slice_constraints.tcl',ROOT/'rtl/asic/slice_openroad.tcl',Path(__file__)]},
                  tools={},simulation={},blocks={})
    def save():
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for tool,flag in (('verilator','--version'),('yosys','-V'),('sta','-version'),('iverilog','-V')):
        manifest['tools'][tool]=command([tool,flag],out,out/f'{tool}_version.log').strip()
    if args.openroad:
        manifest['tools']['openroad']=command([args.openroad,'-version'],out,out/'openroad_version.log').strip()
        manifest['boundary']='Local signal/clock P&R and extracted typical-corner STA; no wafer/HB RC, power grid or power claim'
        manifest['physical_settings']=dict(utilization=30,placement_density=.40,aspect_ratio=1,
            core_space_um=5,seed=42,threads=2,hold_margin_ns=.02,max_hold_buffer_percent=50,
            platform_sha256={str(p.relative_to(args.platform)):sha(p) for p in sorted(args.platform.rglob('*')) if p.is_file()})
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
# Reimport the exported netlist so JSON instance names match OpenSTA reports.
# write_verilog renames private Yosys identifiers; raw pre-export JSON differs.
design -reset
read_liberty -lib {lib}
read_verilog {d/'netlist.v'}
write_json {d/'netlist.json'}
'''
        (d/'synth.ys').write_text(script)
        print('SYNTHESIZE',name,flush=True)
        command(['yosys','-s',d/'synth.ys'],d,d/'synth.log')
        mapped=json.loads((d/'netlist.json').read_text())['modules'][target]
        if tx and mapped['ports']['home_units']['bits'][:3]!=['0','0','0']:
            raise AssertionError('Home units static-output exception no longer valid')
        cells=Counter(c['type'] for c in mapped['cells'].values() if c['type']!='$scopeinfo')
        if any(c.startswith('$') for c in cells):raise AssertionError(f'Unmapped cells: {name}')
        manifest['blocks'][name]=dict(cells=dict(cells),netlist_sha256=sha(d/'netlist.v'),
                                    sequential_cells=sum(v for c,v in cells.items() if c.startswith(('DFF','SDFF'))))
        stats=json.loads((d/'stat.json').read_text())['modules']['\\'+target]
        manifest['blocks'][name].update(cell_area_um2=stats['area'],
                                       sequential_area_um2=stats['sequential_area'])
        env=dict(os.environ,W2W_LIBERTY=str(lib),W2W_NETLIST=str(d/'netlist.v'),
                 W2W_TOP=target,W2W_PERIOD_NS=str(args.period),W2W_TX=str(int(tx)),
                 W2W_HOLD_REPORT=str(d/'hold.tsv'),W2W_SCRIPT_DIR=str(ROOT/'rtl/asic'))
        log=command(['sta','-exit',ROOT/'rtl/asic/slice_sta.tcl'],d,d/'sta.log',env)
        if 'STA_COMPLETE' not in log or re.search(r'(^|\n)Error:',log):
            raise AssertionError(f'STA incomplete: {d}/sta.log')
        manifest['blocks'][name]['sta_complete']=True
        if args.repair:
            before=dict(manifest['blocks'][name])
            repairs=repair_block(d,target,lib,env)
            repaired=json.loads((d/'netlist.json').read_text())['modules'][target]
            cells=Counter(c['type'] for c in repaired['cells'].values() if c['type']!='$scopeinfo')
            stats=json.loads((d/'stat.json').read_text())['modules']['\\'+target]
            manifest['blocks'][name].update(before_repair=before,repair=repairs,
                cells=dict(cells),netlist_sha256=sha(d/'netlist.v'),
                sequential_cells=sum(v for c,v in cells.items() if c.startswith(('DFF','SDFF'))),
                cell_area_um2=stats['area'],sequential_area_um2=stats['sequential_area'])
        if args.openroad:
            before=dict(manifest['blocks'][name])
            initial=d/'initial';initial.mkdir()
            for f in ('netlist.v','netlist.json','stat.json','sta.log','hold.tsv'):
                shutil.copy2(d/f,initial/f)
            physical=d/'physical';physical.mkdir()
            penv=dict(env,W2W_PLATFORM=str(args.platform.resolve()),
                      W2W_PHYSICAL_OUTPUT=str(physical),W2W_HOLD_REPORT=str(physical/'hold.tsv'))
            print('PHYSICAL',name,flush=True)
            log=command([args.openroad,'-no_init','-exit',ROOT/'rtl/asic/slice_openroad.tcl'],
                        physical,physical/'openroad.log',penv)
            if 'PHYSICAL_FLOW_COMPLETE' not in log or 'STA_COMPLETE' not in log:
                raise AssertionError(f'Physical flow incomplete: {physical}')
            shutil.copy2(physical/'netlist.v',d/'netlist.v')
            script=f'''read_liberty -lib {lib}
read_verilog {d/'netlist.v'}
hierarchy -top {target}
check -assert
tee -o {d/'stat.json'} stat -json -liberty {lib} {target}
write_json {d/'netlist.json'}
'''
            (physical/'stat.ys').write_text(script)
            command(['yosys','-s',physical/'stat.ys'],physical,physical/'stat.log')
            post=json.loads((d/'netlist.json').read_text())['modules'][target]
            cells=Counter(c['type'] for c in post['cells'].values() if c['type']!='$scopeinfo')
            stats=json.loads((d/'stat.json').read_text())['modules']['\\'+target]
            import csv
            with (physical/'stages.csv').open() as f: stages=list(csv.DictReader(f))
            metric_lines=(physical/'hold.tsv').read_text().splitlines()
            final_slack={s.split()[1]:float(s.split()[2]) for s in metric_lines if s.startswith('METRIC ')}
            electrical=log.split('=== ELECTRICAL ===')[1]
            drc=re.findall(r'Number of violations\s*=\s*(\d+)',log)
            if not drc:raise AssertionError('Missing routed DRC count')
            passed=min(final_slack.values())>=0 and '(VIOLATED)' not in electrical and int(drc[-1])==0
            manifest['blocks'][name].update(before_physical=before,cells=dict(cells),
                netlist_sha256=sha(d/'netlist.v'),
                sequential_cells=sum(v for c,v in cells.items() if c.startswith(('DFF','SDFF'))),
                cell_area_um2=stats['area'],sequential_area_um2=stats['sequential_area'],
                physical=dict(stages=stages,slack_ns=final_slack,route_drc_count=int(drc[-1]),
                              electrical_violations='(VIOLATED)' in electrical,closed=passed))
        save()
    # Generate zero-delay Liberty cell models; no timing simulation claim.
    # Nangate contains unused clock-gate cells without an IQ function. Skip only
    # unsupported models, then require a model for every actually mapped cell.
    script=f'read_liberty -ignore_miss_func {lib}\nwrite_verilog -noattr {out/"cells.v"}\n'
    (out/'models.ys').write_text(script)
    command(['yosys','-s',out/'models.ys'],out,out/'models.log')
    models=set(re.findall(r'^module\s+(\w+)',(out/'cells.v').read_text(),re.M))
    used={cell for block in manifest['blocks'].values() for cell in block['cells']}
    if used-models:
        raise AssertionError(f'Missing mapped-cell simulation models: {sorted(used-models)}')
    (out/'mapped_star.sv').write_text(mapped_wrapper())
    netlists=[out/name/'netlist.v' for name in manifest['blocks']]
    # Compiled simulation keeps the full archived traces practical at cell level.
    command(['verilator','--binary','--timing','--assert','-Wno-fatal','-j','2',
             '-DPPA_NETLIST','--top-module','endpoint_roundtrip_tb',
             '--Mdir',out/'mapped_obj',out/'cells.v',*netlists,out/'mapped_star.sv',tb],
            out,out/'mapped_build.log')
    manifest['simulation']['mapped_zero_delay']=replay(
        [out/'mapped_obj/Vendpoint_roundtrip_tb'],records,traces,out,'mapped',args.period)
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
    p.add_argument('--repair',action='store_true',help='Bounded cell-level hold/cap ECO under unchanged constraints')
    p.add_argument('--openroad',type=Path,help='OpenROAD executable for matched local physical validation')
    p.add_argument('--platform',type=Path,help='Pinned Nangate45 physical platform directory')
    args=p.parse_args()
    if bool(args.openroad)!=bool(args.platform) or (args.openroad and args.repair):
        p.error('Use --openroad with --platform, starting from unrepaired mapped cells (no --repair)')
    run(args)
