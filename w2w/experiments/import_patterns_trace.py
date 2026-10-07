"""Import authorized local routing files without fetching a dataset or weights."""
import argparse
import json
from pathlib import Path
import subprocess

from w2w.workloads.patterns_trace import compile_patterns, project_demand


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--spec', required=True)
    parser.add_argument('--output', required=True, help='New output directory')
    parser.add_argument('--project-designs', action='store_true', help='Static bytes only; no cycle replay')
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists() and any(output.iterdir()):
        parser.error('Output directory must be new or empty')
    spec = json.loads(Path(args.spec).read_text())
    trace, summary = compile_patterns(args.manifest, spec)
    projections = []
    if args.project_designs:
        from w2w.synthesis.read_catalog import load_designs
        designs, catalog = load_designs()
        summary['projection_catalog'] = catalog
        for design in designs:
            try:
                projections.append(dict(id=design.name, feasible=True,
                                        **project_demand(design, trace, summary['windows'])))
            except ValueError as exc:
                projections.append(dict(id=design.name, feasible=False, reason=str(exc)))
    summary['import_provenance'] = dict(
        commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        source_dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()),
        source_is_observation='Routing evidence only; serving and memory traffic are modeled')
    output.mkdir(parents=True, exist_ok=True)
    for name, record in [('trace.json', trace.record()), ('demand.json', summary), ('execution_spec.json', spec)]:
        (output/name).write_text(json.dumps(record, indent=2, allow_nan=False)+'\n')
    if args.project_designs:
        (output/'residency.json').write_text(json.dumps(projections, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(trace_sha256=trace.sha256, evidence=trace.evidence,
        request_count=len(summary['requests']), layer_windows=len(summary['windows']),
        logical_read_bytes=summary['total_logical_read_bytes'],
        resident_weight_bytes=summary['total_resident_weight_bytes'],
        projected_designs=len(projections), cycle_replay_run=False)))


if __name__ == '__main__':
    main()
