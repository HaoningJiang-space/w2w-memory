"""Audit a completed frozen cohort run before publishing its paired analysis.

Read-only with respect to the replay and frozen inputs. An incomplete or
inconsistent run must fail before producing an analysis or evidence archive.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import tarfile

from w2w.analysis.cohort_replay import summarize
from w2w.provenance import provenance
from w2w.validation.cohort_replay import audit
from w2w.visualization.render_cohort_replay import render
from w2w.workloads.cohort_replay import read_json


def finalize(source, inputs, output):
    source, inputs, output = map(Path, (source, inputs, output))
    if output.exists():
        raise ValueError('Use a fresh finalization directory')
    verified = audit(source, inputs)
    analysis = summarize(source)
    summary = read_json(source / 'summary.json')
    paths = ['summary.json', 'provenance.json', 'completed.jsonl'] + [r['path'] for r in summary['results']]
    # Reject missing evidence before creating the published output directory.
    identities = {p: sha256((source / p).read_bytes()).hexdigest() for p in paths}
    output.mkdir(parents=True)
    (output / 'audit.json').write_text(json.dumps(verified, indent=2)+'\n')
    (output / 'analysis.json').write_text(json.dumps(analysis, indent=2)+'\n')
    import csv
    with (output / 'paired_times.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(analysis['metrics'][0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(analysis['metrics'])
    render(output / 'analysis.json', output / 'mapping_effect')
    archive = output / 'replay_evidence.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name in paths:
            tar.add(source / name, arcname=name, recursive=False)
    receipt = dict(schema='w2w.cohort-finalization.v1', provenance=provenance(),
                   replay_commit=summary['provenance']['commit'], records=verified['records'],
                   delivered_words=verified['delivered_words'], files=identities,
                   inputs_summary_sha256=sha256((inputs/'summary.json').read_bytes()).hexdigest(),
                   archive_sha256=sha256(archive.read_bytes()).hexdigest(),
                   scope=verified['scope'])
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print('AUDITED', receipt['records'], 'replays;', receipt['delivered_words'], 'complete words')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'inputs', 'output'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    finalize(args.source, args.inputs, args.output)


if __name__ == '__main__':
    main()
