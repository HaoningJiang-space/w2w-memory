"""Re-evaluate inequalities from audited activity; no raw replay or simulation."""
import argparse, hashlib, json
from pathlib import Path
from w2w.analysis.energy_edp import threshold
from w2w.common.io import write_json
from w2w.provenance import revision


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--analysis',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Do not overwrite earlier receipts')
    body=a.analysis.read_bytes();r=json.loads(body);m=json.loads(a.manifest.read_text())
    if not r['passed'] or hashlib.sha256(a.manifest.read_bytes()).hexdigest()!=r['manifest_sha256']:
        raise ValueError('Completed reconstruction and matching manifest required')
    for v in r['cases'].values():
        if not v['passed'] or v['raw_result_sha256']!=v['activity']['raw_result_sha256']:
            raise ValueError('Activity/raw receipt binding differs')
    comparisons={k:threshold(r['cases'][base]['activity'],r['cases'][candidate]['activity'])
        for k,(base,candidate) in m['comparisons'].items()}
    write_json(a.output,dict(passed=True,analysis_source_commit=revision(),
        input_analysis_sha256=hashlib.sha256(body).hexdigest(),competition_source_commit=r['analysis_source_commit'],
        comparisons=comparisons,contract='Reuses unchanged SHA-bound activity vectors. Fixed-power energy horizon is drain; EDP latency is output completion. No numerical energy/PPA calibration.'))
    print(json.dumps(dict(passed=True,comparisons=len(comparisons))))


if __name__=='__main__':main()
