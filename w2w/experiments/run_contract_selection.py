"""Audit model-induced design choices using a reproduced endpoint bridge."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from w2w.synthesis.contract_selection import study
from w2w.analysis.analyze_endpoint_bridge import check


def main():
    p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('--output',required=True);a=p.parse_args()
    if subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise RuntimeError('Clean source required')
    check(a.input)
    raw=Path(a.input).read_bytes();result=study(json.loads(raw))
    result.update(commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                  input_sha256=hashlib.sha256(raw).hexdigest())
    target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2)+'\n')
    for model in ('optimistic','fluid'):
        rows=[r for r in result['selections'] if r['selector']==model and r['selected']]
        print(model,'selected',len(rows),'floor violations',sum(not r['actual_floor_feasible'] for r in rows),
              'max feasible regret',max((r['regret'] or 0) for r in rows))
    print('FRONTIER',result['frontier'])


if __name__=='__main__':main()
