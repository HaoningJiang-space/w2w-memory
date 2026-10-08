"""One-factor control: general source versus deployment-specialized pruning.

No new endpoint, placement, residency, request trace or timing model is added.
Synthesis area is kept separate from old post-route figures and wafer costs.
"""
import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
CASES = {'duplicated': (False, 0, 0), 'configurable': (False, 1, 0),
         'pruned_dup_l': (True, 0, 0), 'pruned_dup_r': (True, 0, 1),
         'pruned_cfg_l': (True, 1, 0), 'pruned_cfg_r': (True, 1, 1)}


def file_hash(path): return sha256(Path(path).read_bytes()).hexdigest()


def command(argv, folder, log):
    with Path(log).open('w') as stream:
        result = subprocess.run([str(x) for x in argv], cwd=folder, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode: raise RuntimeError(f'Command failed: {argv[0]}, see {log}')
    return Path(log).read_text()


def paired_wrapper(candidate):
    ports = '''input wire clk,rst,cfg_shared_direction,
    input wire native_valid,native_role,native_shared_direction,
    input wire [255:0] native_data,output wire native_ready,
    input wire [2:0] sink_ready,output wire [2:0] sink_valid,
    output wire [767:0] sink_data,output wire [2:0] hb_valid,hb_ready,
    output wire [767:0] hb_data,output wire [11:0] hb_units'''
    text = '`timescale 1ns/1ps\n'
    for suffix, source in (('dup', 'mapped_'+candidate), ('cfg', 'mapped_configurable')):
        text += f'''module endpoint_ppa_{suffix} ({ports});
    wire [255:0] hd; wire [159:0] ld,rd;
    {source} tx (.clk(clk),.rst(rst),.cfg_shared_direction(cfg_shared_direction),
      .native_valid(native_valid),.native_role(native_role),
      .native_shared_direction(native_shared_direction),.native_data(native_data),
      .native_ready(native_ready),.hb_valid(hb_valid),.hb_ready(hb_ready),
      .home_data(hd),.left_data(ld),.right_data(rd),
      .home_units(hb_units[3:0]),.left_units(hb_units[7:4]),.right_units(hb_units[11:8]));
    assign hb_data={{96'b0,rd,96'b0,ld,hd}};
'''
        for index, (width, data) in enumerate(((256, 'hd'), (160, 'ld'), (160, 'rd'))):
            text += f'''    endpoint_rx #(.WIDTH({width})) rx{index} (
      .clk(clk),.rst(rst),.beat_valid(hb_valid[{index}]),.beat_ready(hb_ready[{index}]),
      .beat_data({data}),.beat_units(hb_units[{4*index}+:4]),
      .word_valid(sink_valid[{index}]),.word_ready(sink_ready[{index}]),
      .word_data(sink_data[{256*index}+:256]));\n'''
        text += 'endmodule\n'
    return text


def run(args):
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise RuntimeError('Use committed clean source')
    out, lib, traces = args.output.resolve(), args.liberty.resolve(), args.traces.resolve()
    out.mkdir(parents=True, exist_ok=False)
    rtl = [ROOT/'rtl/cse_bank.sv', ROOT/'rtl/endpoint_link.sv', ROOT/'rtl/baselines/endpoint_fixed_source.sv']
    archive = ROOT/'artifacts/results/endpoint/endpoint_roundtrip.json.gz'
    records = [r for r in json.loads(gzip.decompress(archive.read_bytes()))['records'] if r['width'] == 160]
    for r in records:
        for kind in ('words', 'controls'):
            path = traces/f'{r["pattern"]}_dir{r["direction"]}'/f'{kind}.txt'
            if file_hash(path) != r[f'{kind}_sha256']: raise ValueError('Frozen native trace changed')
    manifest = dict(schema='w2w.static-binding-baseline.v1',
        source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        library_sha256=file_hash(lib), rtl_sha256={str(p.relative_to(ROOT)): file_hash(p) for p in rtl},
        trace_archive_sha256=file_hash(archive), period_ns=2, blocks={}, simulations={},
        scope='Source-only Nangate45 mapping; no STA closure, P&R, HB/pad/RX savings or whole-wafer claim',
        deployment_scope='Fixed candidates specialize one direction before manufacturing; configurable retains both choices',
        tools={t: subprocess.check_output([t, flag], text=True).strip()
               for t, flag in (('yosys', '-V'), ('verilator', '--version'))})
    def save(): (out/'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (out/'abc.constr').write_text('set_driving_cell BUF_X1\nset_load 5.0\n')
    for name, (fixed, cfg, direction) in CASES.items():
        folder = out/name; folder.mkdir()
        top = 'endpoint_fixed_source' if fixed else 'endpoint_source'
        params = f'-set CONFIGURABLE {cfg} ' + (f'-set DIRECTION {direction}' if fixed else '-set WIDTH 160 -set DEPTH 2')
        script = f'''read_verilog -sv -DSYNTHESIS {' '.join(map(str, rtl))}
chparam {params} {top}
synth -top {top} -flatten -noabc
dfflibmap -liberty {lib}
abc -liberty {lib} -constr {out/'abc.constr'} -D 2000
clean
read_liberty -lib {lib}
check -assert
rename {top} mapped_{name}
tee -o {folder/'stat.json'} stat -json -liberty {lib} mapped_{name}
select mapped_{name}
write_verilog -noattr -noexpr -selected {folder/'netlist.v'}
write_json {folder/'netlist.json'}
'''
        (folder/'synth.ys').write_text(script)
        command(['yosys', '-s', folder/'synth.ys'], folder, folder/'synth.log')
        module = json.loads((folder/'netlist.json').read_text())['modules']['mapped_'+name]
        cells = Counter(c['type'] for c in module['cells'].values())
        if any(k.startswith('$') for k in cells): raise ValueError('Unmapped cell')
        stat = json.loads((folder/'stat.json').read_text())['modules']['\\mapped_'+name]
        manifest['blocks'][name] = dict(area_um2=stat['area'], cells=dict(cells),
            sequential_cells=sum(v for c, v in cells.items() if c.startswith(('DFF', 'SDFF'))),
            netlist_sha256=file_hash(folder/'netlist.v'), stat_sha256=file_hash(folder/'stat.json'))
        save(); print('MAPPED', name, manifest['blocks'][name]['area_um2'], flush=True)
    (out/'models.ys').write_text(f'read_liberty -ignore_miss_func {lib}\nwrite_verilog -noattr {out/"cells.v"}\n')
    command(['yosys', '-s', out/'models.ys'], out, out/'models.log')
    for name in ('pruned_dup_l', 'pruned_dup_r', 'pruned_cfg_l', 'pruned_cfg_r'):
        folder = out/name
        wrapper = folder/'paired.sv'; wrapper.write_text(paired_wrapper(name))
        command(['verilator', '--binary', '--timing', '--assert', '-Wno-fatal', '-j', '2',
                 '-DSYNTHESIS', '-DPPA_NETLIST', '--top-module', 'endpoint_roundtrip_tb',
                 '--Mdir', folder/'obj', out/'cells.v', folder/'netlist.v',
                 out/'configurable/netlist.v', *rtl[:2], wrapper, ROOT/'rtl/endpoint_roundtrip_tb.sv'],
                out, folder/'compile.log')
        results = []
        for r in records:
            if r['direction'] != CASES[name][2]: continue
            case = f'{r["pattern"]}_dir{r["direction"]}'
            text = command([folder/'obj/Vendpoint_roundtrip_tb', f'+DIR={r["direction"]}', '+PERIOD_NS=2',
                            f'+WORDS={traces/case/"words.txt"}', f'+CONTROLS={traces/case/"controls.txt"}'],
                           out, folder/f'{case}.log')
            line = next(s for s in text.splitlines() if s.startswith('RESULT '))
            values = list(map(int, line.split()[1:]))
            expected = [r['accepted'], *r['received'], *r['measured_received'], r['measured_accepted'],
                        r['source_stall_cycles'], r['hb_stall_port_cycles'], r['rx_stall_port_cycles']]
            if values[1:12] != expected: raise ValueError('Frozen service counters changed')
            results.append(dict(case=case, result=values))
        manifest['simulations'][name] = results
        save(); print('VERIFIED', name, len(results), 'paired mapped cases', flush=True)
    manifest['complete'] = True
    save()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--liberty', type=Path, required=True)
    p.add_argument('--traces', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    run(p.parse_args())


if __name__ == '__main__': main()
