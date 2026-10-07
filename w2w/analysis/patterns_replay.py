"""Audit registered routing replays and export their report (stable CLI)."""
import argparse
import csv
import json
from pathlib import Path

# Compatibility exports; reusable validation lives below the reporting layer.
from w2w.validation.patterns_replay import (
    audit, check_coverage, check_delivery, check_routing_union, expected_keys,
)
from w2w.visualization.render_patterns_replay import render as render_figure


def render(report, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
    with (output / 'replays.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report['rows'][0]))
        writer.writeheader()
        writer.writerows(report['rows'])
    render_figure(report, output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--plan', default='artifacts/provenance/patterns_replay/plan.json')
    parser.add_argument('--verify-inputs', action='store_true')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = audit(args.source, args.plan, args.verify_inputs)
    render(report, args.output)
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}))
