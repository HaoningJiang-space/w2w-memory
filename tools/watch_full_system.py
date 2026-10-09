#!/usr/bin/env python3
"""Bounded read-only periodic completion checks; exits after success or a logged failure."""
import argparse
import json
from pathlib import Path
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--study',type=Path,required=True)
p.add_argument('--logs',type=Path,required=True)
p.add_argument('--interval',type=int,default=60)
p.add_argument('--checks',type=int,default=240)
args=p.parse_args()
if args.interval<1 or args.checks<1:p.error('Positive interval/check count required')
registration=json.loads((args.study/'registration.json').read_text())
names=[c['name'] for c in registration['cases']]
for _ in range(args.checks):
    status={}
    for name in names:
        done=args.study/'cases'/name/'completion.json'
        log=args.logs/(name+'.log')
        if done.exists():status[name]=json.loads(done.read_text())
        elif log.exists() and 'Traceback (most recent call last)' in log.read_text():status[name]={'failed':True}
        else:status[name]={'running_or_pending':True}
    print(json.dumps(dict(time_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),cases=status)),flush=True)
    if all(v.get('complete') for v in status.values()):break
    if any(v.get('failed') for v in status.values()):raise SystemExit(1)
    time.sleep(args.interval)
else:raise SystemExit('Periodic monitor reached its explicit check limit')
