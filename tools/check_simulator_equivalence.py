#!/usr/bin/env python3
"""Compare complete physical records, allowing only build/provenance differences."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control


def canonical(record):
    r=copy.deepcopy(record)
    for name in ('source_commit','audit','control_audit'):r.pop(name,None)
    r['network'].pop('runtime_source',None)
    for name in ('binary_sha256','config_sha256'):r['network']['identity'].pop(name,None)
    return r


def protocol_digest(path):
    h=hashlib.sha256();count=0
    for line in path.open():
        r=json.loads(line)
        if 'request' in r:
            if r['request']['command']=='advance':continue
            if r['request']['command']=='close':continue
            rows=[r]
        else:
            reply=r['reply']
            rows=[dict(progress=e) for e in reply.get('progress',())]
            rows.extend(dict(completed=e) for e in reply.get('completed',()))
        for row in rows:
            h.update(json.dumps(row,sort_keys=True,separators=(',',':')).encode()+b'\n');count+=1
    return dict(sha256=h.hexdigest(),events=count)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--detailed',action='store_true')
    a=p.parse_args();records=[]
    for directory in (a.baseline,a.candidate):
        with gzip.open(directory/'result.json.gz','rt') as f:r=json.load(f)
        audit_vertical_result(r);audit_request_control(r);records.append(canonical(r))
    if records[0]!=records[1]:
        differing=[k for k in records[0] if records[0][k]!=records[1].get(k)]
        raise ValueError('Physical records differ: '+str(differing))
    proof=dict(passed=True,makespan_ps=records[0]['makespan_ps'],drained_ps=records[0]['drained_ps'],
        events=len(records[0]['events']),physical_record_equal=True,
        allowed_differences=['source commit','native binary/config file identity','Python runtime file fingerprints'])
    if a.detailed:
        traces=[protocol_digest(d/'network/online_protocol.jsonl') for d in (a.baseline,a.candidate)]
        if traces[0]!=traces[1]:raise ValueError('Flit/VC/endpoint supply/commit events differ')
        proof['network_trace']=traces[0]
        commands=[]
        for d in (a.baseline,a.candidate):
            files=sorted(d.glob('commands.ch*'));h=hashlib.sha256()
            if not files:raise ValueError('Missing native command evidence')
            for f in files:h.update(f.name.encode());h.update(f.read_bytes())
            commands.append(h.hexdigest())
        if commands[0]!=commands[1]:raise ValueError('Native command/time/address traces differ')
        proof['commands_sha256']=commands[0]
    a.output.write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n');print(json.dumps(proof))


if __name__=='__main__':main()
