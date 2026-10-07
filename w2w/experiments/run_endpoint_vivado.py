"""Matched FPGA slice implementation; run remotely with Vivado in PATH."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args, cwd, log, env=None):
    with log.open('w') as stream:
        result = subprocess.run([str(a) for a in args], cwd=cwd, env=env,
                                stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed ({result.returncode}): {log}')
    return log.read_text(errors='replace')


def run(args):
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    reference_path = ROOT/'artifacts/results/endpoint/endpoint_roundtrip.json.gz'
    with gzip.open(reference_path, 'rt') as stream:
        reference = json.load(stream)
    records = [r for r in reference['records'] if r['width'] == 160]
    traces = args.traces.resolve()
    for r in records:
        case = traces/f'{r["pattern"]}_dir{r["direction"]}'
        for name in ('words', 'controls'):
            if digest(case/f'{name}.txt') != r[f'{name}_sha256']:
                raise ValueError(f'Archived trace mismatch: {case}/{name}.txt')
    sources = [ROOT/'rtl'/name for name in
               ('cse_bank.sv', 'endpoint_link.sv', 'endpoint_roundtrip_tb.sv')]
    inputs = sources + list((ROOT/'rtl/vivado').glob('*.tcl')) + [Path(__file__),
             ROOT/'docs/methods/ENDPOINT_VIVADO_SLICE.md', reference_path]
    manifest = dict(started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    part=args.part, period_ns=args.period,
                    file_sha256={str(p.relative_to(ROOT)): digest(p) for p in inputs},
                    reference='2745632 RTL / 78384d9 archived roundtrip',
                    scope='Separately routed local FPGA blocks; no ASIC or HB PPA', records=[])
    source_stamp = ROOT/'SOURCE_COMMIT'
    manifest['source_revision'] = source_stamp.read_text().strip() if source_stamp.exists() else subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    manifest['tool_version'] = command(['vivado', '-version'], out, out/'version.log')
    sim = out/'sim'
    reuse = None
    if args.simulation_from:
        previous = args.simulation_from.resolve()
        reuse = json.loads((previous/'manifest.json').read_text())
        assert reuse['period_ns'] == args.period
        for path in sources + [ROOT/'rtl/vivado/slice_saif.tcl', reference_path]:
            key = str(path.relative_to(ROOT))
            assert reuse['file_sha256'][key] == manifest['file_sha256'][key], key
        assert len(reuse['records']) == len(records)
        sim = previous/'sim'
        manifest['simulation_provenance'] = dict(source_revision=reuse['source_revision'],
            manifest_sha256=digest(previous/'manifest.json'), directory=str(previous))
    else:
        sim.mkdir(exist_ok=True)
        command(['xvlog', '--sv', *sources], sim, sim/'compile.log')
        # Top-level generic overrides change XSim's root scope name; use a plusarg.
        command(['xelab', 'endpoint_roundtrip_tb', '-s', 'slice', '-debug', 'typical', '-mt', '2'],
                sim, sim/'elaborate.log')
    for r in records:
        name = f'{r["pattern"]}_dir{r["direction"]}'
        case = sim/name
        case.mkdir(exist_ok=True)
        if reuse:
            record = next(v for v in reuse['records'] if v['case'] == name)
            assert record['archived_counts_match']
            if r['pattern'] in ('mixed', 'stalls'):
                assert (case/'activity.saif').stat().st_size > 1000
            manifest['records'].append(record)
            continue
        env = dict(os.environ)
        env.pop('W2W_SAIF_FILE', None)
        if r['pattern'] in ('mixed', 'stalls'):
            env['W2W_SAIF_FILE'] = str(case/'activity.saif')
            env['W2W_PERIOD_NS'] = str(args.period)
        log = command(['xsim', 'slice', '-tclbatch', ROOT/'rtl/vivado/slice_saif.tcl',
                       '-testplusarg', f'PERIOD_NS={args.period}',
                       '-testplusarg', f'DIR={r["direction"]}',
                       '-testplusarg', f'WORDS={traces/name/"words.txt"}',
                       '-testplusarg', f'CONTROLS={traces/name/"controls.txt"}'],
                      sim, case/'run.log', env)
        line = next((s for s in log.splitlines() if s.startswith('RESULT ')), None)
        if line is None or 'Fatal:' in log:
            raise AssertionError(f'XSim scoreboard failed: {case}/run.log')
        values = list(map(int, line.split()[1:]))
        expected = [r['accepted'], *r['received'], *r['measured_received'],
                    r['measured_accepted'], r['source_stall_cycles'],
                    r['hb_stall_port_cycles'], r['rx_stall_port_cycles'],
                    r['maximum_pending_payload_bits']]
        if values[1:] != expected:
            raise AssertionError(f'XSim/archive mismatch: {name}: {values[1:]} != {expected}')
        manifest['records'].append(dict(case=name, result=values, archived_counts_match=True))
        (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        print('XSIM_VERIFIED', name, flush=True)
    for block in ('tx_dup', 'tx_cfg', 'rx_home', 'rx_shared'):
        folder = out/block
        folder.mkdir(exist_ok=True)
        print('IMPLEMENT', block, flush=True)
        command(['vivado', '-mode', 'batch', '-nojournal', '-log', folder/'vivado.log',
                 '-source', ROOT/'rtl/vivado/slice_impl.tcl', '-tclargs',
                 ROOT, folder, block, args.part, args.period, sim],
                folder, folder/'console.log')
        manifest.setdefault('implemented', []).append(block)
        (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    manifest['completed_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('COMPLETE', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--traces', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--part', default='xc7z020clg484-1')
    parser.add_argument('--period', type=float, default=2.0)
    parser.add_argument('--simulation-from', type=Path,
                        help='Reuse matching, completed XSim evidence when only implementation changes')
    run(parser.parse_args())
