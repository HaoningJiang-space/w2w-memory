"""Sequential saved-record analysis, SHA-bound to existing independent audits.

This is a reader, not a simulator launcher. Retain a checkpoint after each case
to avoid keeping multiple large application event records in memory.
"""
import argparse, gc, gzip, hashlib, json, time
from pathlib import Path
from w2w.analysis.compute_memory_competition import competition
from w2w.analysis.energy_edp import activity, threshold
from w2w.common.io import write_json
from w2w.provenance import revision


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024**2),b''):h.update(chunk)
    return h.hexdigest()


def analyze(manifest, output):
    rows={}
    for label,entry in manifest['cases'].items():
        path=Path(entry['raw']);checkpoint=output/f'{label}.json'
        if checkpoint.exists():raise ValueError('Use a new output directory; never overwrite a readback')
        proof=json.loads(Path(entry['audit']).read_text())
        if not proof['passed']:raise ValueError('Completed independent audit required')
        raw_sha=proof['files'][entry['audit_raw_key']]['sha256']
        if sha(path)!=raw_sha:raise ValueError('Saved result changed after its independent audit')
        before=time.monotonic()
        with gzip.open(path,'rt') as f:r=json.load(f)
        expected=proof['cases'][entry['audit_case']]
        if r['makespan_ps']!=expected['makespan_ps'] or r['source_commit']!=proof['execution_source_commit']:
            raise ValueError('Execution identity differs from independent audit')
        vector=activity(r);vector['raw_result_sha256']=raw_sha
        record=dict(passed=True,raw=entry['raw'],raw_result_sha256=raw_sha,
            audit_sha256=sha(Path(entry['audit'])),execution_source_commit=r['source_commit'],
            analysis_source_commit=revision(),makespan_ps=r['makespan_ps'],activity=vector,
            competition=competition(r),reader_wall_seconds=time.monotonic()-before)
        write_json(checkpoint,record);rows[label]=record
        print(json.dumps(dict(case=label,passed=True,reader_wall_seconds=record['reader_wall_seconds'])),flush=True)
        del r,proof;gc.collect()
    comparisons={}
    for name,(base,candidate) in manifest['comparisons'].items():
        comparisons[name]=threshold(rows[base]['activity'],rows[candidate]['activity'])
    result=dict(schema='w2w.competition-energy-readback.v1',passed=True,analysis_source_commit=revision(),
        cases=rows,comparisons=comparisons,manifest_sha256=manifest['_sha256'],
        limits='Independent audited raw SHA binding; no hardware execution change, simulation retry, calibrated energy or PPA claim.')
    write_json(output/'analysis.json',result)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();m=json.loads(a.manifest.read_text());m['_sha256']=sha(a.manifest)
    a.output.mkdir(parents=True,exist_ok=False);analyze(m,a.output)
