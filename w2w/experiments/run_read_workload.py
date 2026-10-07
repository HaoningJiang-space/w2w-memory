"""Frozen H/plus designs replay the same logical read DAG and cost contract."""
import argparse
from dataclasses import asdict, replace
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import time

from w2w.analysis.read_completion import completion_metrics, projected_frontier
from w2w.domain import EndpointSpec
from w2w.domain.endpoint import NativeProfile
from w2w.provenance import provenance
from w2w.service.cost import CostModel
from w2w.service.guaranteed_service_exchange import contoured_geometry
from w2w.service.read_replay import ReadReplayConfig, replay_reads
from w2w.synthesis.role_interfaces import make_candidate, static_shared_fifo
from w2w.workloads.moe_reads import compile_moe_reads, synthetic_moe_captures
from w2w.workloads.read_trace import ReadTrace, digest, synthetic_read_suite


CATALOG = 'artifacts/results/endpoint/architecture_competition.json.gz'
PREFIX = 'k3_23_random9_maxweight_'
DESIGNS = ('home_h256s0_d00_direct', 'k2_23_h256s256_d00_direct',
           PREFIX + 'h256s256_d00_direct', PREFIX + 'h256s128_d11_buffered',
           PREFIX + 'h256s160_d12_buffered')


def load_designs(path=CATALOG):
    raw = Path(path).read_bytes()
    archive = json.loads(gzip.decompress(raw) if str(path).endswith('.gz') else raw)
    rows = {row['id']: row for row in archive['search']['catalog']}
    physical = contoured_geometry()
    designs = []
    for key in DESIGNS:
        row = rows[key]
        spec = EndpointSpec(**{**row['endpoint'], 'native': NativeProfile(**row['endpoint']['native'])})
        design = make_candidate(physical, row['pairs'], key, row['structure'], spec,
                                Fraction(row['home_fraction']), row['directions'], allow_unmatched=True)
        if design.layout.sha256 != row['layout_hash']:
            raise RuntimeError('Archived frozen layout failed reconstruction')
        cost = CostModel.evaluate(design)
        if any(cost[k] != v for k, v in row['cost'].items()):
            raise RuntimeError('Archived cost contract changed')
        designs.append(design)
    designs.extend(static_shared_fifo(d, share_serializer=True) for d in tuple(designs)
                   if d.structure == 'k3' and d.endpoint.mode == 'buffered')
    return designs, dict(path=str(path), file_sha256=sha256(raw).hexdigest(),
                         source_commit=archive['provenance']['commit'],
                         selection='Five preregistered archived representatives plus two implementation ablations; '
                                   'no layout or interface search on evaluation requests')


def hardware_evidence(path, rows):
    """Join supplied measurement artifacts by full design identity, never by name."""
    if path is None:
        return []
    path = Path(path)
    records = json.loads(path.read_text())
    known = {r['design_sha256'] for r in rows}
    result = []
    for record in records:
        required = {'design_sha256', 'artifact', 'artifact_sha256', 'source_commit',
                    'scope', 'timing_closed', 'measurements'}
        if set(record) != required or record['design_sha256'] not in known:
            raise ValueError('Hardware evidence must bind to an evaluated full design hash')
        artifact = path.parent / record['artifact']
        if sha256(artifact.read_bytes()).hexdigest() != record['artifact_sha256']:
            raise ValueError('Hardware artifact hash mismatch')
        if type(record['timing_closed']) is not bool or not record['scope'] or not record['source_commit']:
            raise ValueError('Hardware scope, timing status and source commit required')
        result.append(record)
    return result


def evaluate_designs(designs, trace, config):
    rows = []
    for design in designs:
        row = replay_reads(design, trace, config)
        row['id'] = design.name
        row['cost'] = CostModel.evaluate(design)
        row['completion'] = completion_metrics(trace, row)
        row['additional_model_resources'] = dict(
            rx_payload_bits_per_memory=(row['cost']['bank_port_connections'] * config.rx_depth_words
                                        * design.endpoint.word_bits),
            rx_scope='Full manufactured bank/output template, including unused directions; model allocation only',
            request_outstanding_words_per_compute=config.outstanding_words_per_compute,
            request_issue_words_per_compute_slot=config.request_words_per_compute_slot,
            metadata_logic_area=None, request_path_area=None, physical_support_area=None,
            note='Request metadata, valid/ready, RX control and physical support are not calibrated; '
                 'do not sum model bits, standard-cell area and wire bit-mm')
        rows.append(row)
        print('REPLAY', design.name, 'slots', row['makespan_slots'],
              'words', row['audit']['delivered_words'], flush=True)
    by_id = {r['id']: r for r in rows}
    ablations = []
    for name in DESIGNS[-2:]:
        old, new = by_id[name], by_id[name + '_shared_egress']
        keys = ('trace_sha256', 'residence_sha256', 'config', 'makespan_slots', 'tasks',
                'routes', 'audit', 'delivery_sha256', 'stalls', 'native_words_by_bank',
                'peak_outstanding_words')
        if any(old[k] != new[k] for k in keys):
            raise RuntimeError('Duplicated/configurable service ablation diverged')
        ablations.append(dict(duplicated=name, configurable=new['id'], compared_fields=list(keys),
                              equal=True, scope='Same static requests and bit-budget model, not RTL equivalence'))
    return rows, ablations


def run(args):
    if subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip():
        raise RuntimeError('Commit source before experiment; use an isolated clean checkout')
    if args.suite:
        return run_suite(args)
    started = time.monotonic()
    if args.demo:
        training, evaluation = synthetic_moe_captures()
        trace, imported = compile_moe_reads(training, evaluation)
        inputs = dict(training=training, evaluation=evaluation)
    elif args.trace:
        raw = Path(args.trace).read_bytes()
        trace = ReadTrace.from_record(json.loads(raw))
        imported = dict(policy='User-supplied frozen logical ownership and dependencies',
                        file_sha256=sha256(raw).hexdigest())
        inputs = dict(trace_file=str(args.trace))
    else:
        training_raw, evaluation_raw = Path(args.training_routes).read_bytes(), Path(args.routes).read_bytes()
        training, evaluation = json.loads(training_raw), json.loads(evaluation_raw)
        trace, imported = compile_moe_reads(training, evaluation)
        inputs = dict(training=training, evaluation=evaluation,
                      training_file_sha256=sha256(training_raw).hexdigest(),
                      evaluation_file_sha256=sha256(evaluation_raw).hexdigest())
    config = ReadReplayConfig(**json.loads(Path(args.config).read_text())) if args.config else ReadReplayConfig()
    designs, archive = load_designs(args.catalog)
    rows, ablations = evaluate_designs(designs, trace, config)
    evidence = hardware_evidence(args.hardware_evidence, rows)
    result = dict(schema='w2w.read-workload-study.v1', provenance=provenance(),
                  registration_sha256=sha256(Path('docs/methods/READ_WORKLOAD_REPLAY.md').read_bytes()).hexdigest(),
                  archive=archive, inputs=inputs, import_record=imported, trace=trace.record(),
                  trace_sha256=trace.sha256, config=asdict(config), results=rows, ablations=ablations,
                  hardware_evidence=evidence, hardware_evidence_complete=False,
                  claim='Infrastructure replay of fixed candidates; no new architecture optimum or application speedup',
                  elapsed_seconds=time.monotonic() - started)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    summary = dict(trace_sha256=trace.sha256, evidence=trace.evidence,
                   results=[{k: r[k] for k in ('id', 'design_sha256', 'residence_sha256',
                                               'makespan_slots', 'makespan_ns', 'logical_bytes',
                                               'effective_tb_s', 'summed_task_read_wait_slots', 'cost')}
                            for r in rows], ablations=ablations,
                   elapsed_seconds=result['elapsed_seconds'])
    output.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('VERIFIED', len(rows), 'designs;', len(ablations), 'equal service ablations;',
          'evidence', trace.evidence, 'seconds', result['elapsed_seconds'], flush=True)


def run_suite(args):
    started = time.monotonic()
    designs, archive = load_designs(args.catalog)
    traces = synthetic_read_suite(designs[0].geometry.compute_xy)
    base = ReadReplayConfig()
    cases = [(name, 'base', trace, base) for name, trace in traces.items()]
    cases.extend((name, 'credits512', traces[name], replace(base, outstanding_words_per_compute=512))
                 for name in ('dispersed9', 'clustered9', 'full36'))
    cases.append(('dispersed9', 'rx_half', traces['dispersed9'], replace(base, rx_ready=(1, 1, 0, 0))))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    results, summary = [], []
    for name, control, trace, config in cases:
        print('CASE', name, control, flush=True)
        rows, ablations = evaluate_designs(designs, trace, config)
        home = rows[0]['makespan_slots']
        for row in rows:
            row['speedup_vs_home'] = home / row['makespan_slots']
        record = dict(case=name, control=control, trace=trace.record(), trace_sha256=trace.sha256,
                      config=asdict(config), results=rows, ablations=ablations,
                      projected_frontier=projected_frontier(rows))
        path = output / f'{name}_{control}.json.gz'
        data = gzip.compress((json.dumps(record, separators=(',', ':'), allow_nan=False) + '\n').encode(), mtime=0)
        path.write_bytes(data)
        results.append(dict(case=name, control=control, path=path.name,
                            sha256=sha256(data).hexdigest(), trace_sha256=trace.sha256))
        summary.append(dict(case=name, control=control, config=asdict(config), ablations=ablations,
                            projected_frontier=record['projected_frontier'],
                            rows=[{k: r[k] for k in ('id', 'design_sha256', 'residence_sha256',
                                  'makespan_slots', 'logical_bytes', 'speedup_vs_home', 'completion',
                                  'summed_task_read_wait_slots', 'cost', 'stalls', 'audit')}
                                  for r in rows]))
    # Same object population gives exactly the same frozen addresses in all cases.
    for design in designs:
        hashes = {r['residence_sha256'] for case in summary for r in case['rows'] if r['id'] == design.name}
        if len(hashes) != 1:
            raise RuntimeError('Workload or credit control changed frozen residence')
    result = dict(schema='w2w.finite-read-study.v1', provenance=provenance(), archive=archive,
                  registration_sha256=sha256(Path('docs/methods/FINITE_READ_STUDY.md').read_bytes()).hexdigest(),
                  evidence='synthetic', cases=summary, artifacts=results,
                  comparison_unit='native slots; model 1.024 ns/slot is not ASIC 2 ns clock validation',
                  scope='77 finite DAG replays of frozen representatives; known cost projection only; '
                        'no RTL-cycle equivalence, calibrated ASIC/system PPA or application speedup',
                  elapsed_seconds=time.monotonic() - started)
    (output / 'summary.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print('VERIFIED', len(cases) * len(designs), 'replays;', 2 * len(cases),
          'equal implementation ablations; seconds', result['elapsed_seconds'], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--suite', action='store_true', help='Registered finite synthetic task study')
    source.add_argument('--demo', action='store_true', help='Explicitly synthetic infrastructure fixture')
    source.add_argument('--trace', help='w2w.read-trace.v1 logical DAG JSON')
    source.add_argument('--routes', help='w2w.moe-routes.v1 test routing capture')
    parser.add_argument('--training-routes', help='Disjoint training routing capture for static expert balance')
    parser.add_argument('--catalog', default=CATALOG)
    parser.add_argument('--config', help='ReadReplayConfig JSON overrides')
    parser.add_argument('--hardware-evidence', help='Optional design-bound artifact references; separate units/scopes')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if bool(args.routes) != bool(args.training_routes):
        parser.error('--routes and --training-routes must be provided together')
    if args.suite and (args.config or args.hardware_evidence):
        parser.error('--suite uses registered configurations and keeps ASIC evidence separate')
    run(args)


if __name__ == '__main__':
    main()
