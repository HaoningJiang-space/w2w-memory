"""Archive isolated count-level link states without altering finite replay."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from w2w.provenance import provenance
from w2w.theory.beat_return import beat_path_period


def run(output):
    prov=provenance()
    if prov['git_status']:
        raise ValueError('Clean source required')
    cases=[]
    for width,depth in ((128,1),(160,2),(192,2),(256,1)):
        for stages in (0,1,2,4):
            for slots in (1,2):
                cases.append(beat_path_period(width,depth,stages,slots))
        for pattern in ((0,),(1,0),(1,1,1,1,0,0,0,0),(0,)*31+(1,)*17):
            cases.append(beat_path_period(width,depth,4,2,pattern))
    record=dict(schema='w2w.beat-return-contract.v1',provenance=prov,cases=cases,
        registration_sha256=sha256(Path('docs/methods/BEAT_RETURN_CONTRACT.md').read_bytes()).hexdigest(),
        rtl_source_sha256={p:sha256(Path(p).read_bytes()).hexdigest() for p in ('rtl/endpoint_link.sv','rtl/cse_bank.sv')})
    Path(output).write_text(json.dumps(record,indent=2)+'\n')
    print('VERIFIED',len(cases),'count-level recurrence witnesses; no RTL run')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True)
    run(p.parse_args().output)
