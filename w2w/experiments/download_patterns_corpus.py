"""Bounded, seeded, multi-subject routing corpus; secrets only go to HF origin."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import time
import sys
from urllib.error import URLError

from w2w.workloads.patterns_download import fetch


def download(plan, output, token_file=None, token=None):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    subjects = plan['subjects']
    if not subjects or len(set(subjects)) != len(subjects):
        raise ValueError('Unique explicit subjects required')
    per_subject = plan['max_total_bytes']//len(subjects)
    def one(subject):
        for attempt in range(3):
            try:
                result = fetch('https://huggingface.co', plan['model_prefix']+'/'+subject,
                    output/subject, plan['requests_per_subject'], plan['max_file_bytes'],
                    per_subject, token_file, selection='seeded', seed=plan['download_seed'],
                    resume=True, revision=plan['revision'], token=token)
                if len(result['downloaded']) != plan['requests_per_subject']:
                    raise ValueError('Insufficient files within registered size limits: '+subject)
                return subject,result
            except (URLError, TimeoutError, ConnectionResetError):
                if attempt == 2:raise
                time.sleep(attempt+1)
    results = {}
    with ThreadPoolExecutor(max_workers=min(4,len(subjects))) as pool:
        futures = [pool.submit(one,s) for s in subjects]
        for future in as_completed(futures):
            subject,record=future.result();results[subject]=record
            print(json.dumps(dict(subject=subject,files=len(record['downloaded']),
                                 bytes=sum(x['bytes'] for x in record['downloaded']))),flush=True)
    entries=[];total=0
    for subject in subjects:
        for row in results[subject]['downloaded']:
            entries.append(dict(id=row['source_path'],path=subject+'/'+row['path'],
                                sha256=row['sha256'],arrival_iteration=0))
            total+=row['bytes']
    assert total <= plan['max_total_bytes']
    if len({r['id'] for r in entries}) != len(entries) or len({r['sha256'] for r in entries}) != len(entries):
        raise ValueError('Duplicate source request or identical routing content; inspect before analysis')
    manifest=dict(schema='w2w.pbc-files.v1',evidence='captured',
                  source='https://huggingface.co/datasets/core12345/MoE_expert_selection_trace',
                  revision=plan['revision'],requests=entries)
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (output/'study_plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps(dict(total_requests=len(entries),raw_bytes=total)),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',required=True);p.add_argument('--output',required=True)
    credentials=p.add_mutually_exclusive_group(required=True)
    credentials.add_argument('--token-file')
    credentials.add_argument('--token-stdin',action='store_true',help='Read token from encrypted stdin; do not persist it')
    args=p.parse_args()
    token=sys.stdin.readline().strip() if args.token_stdin else None
    download(json.loads(Path(args.plan).read_text()),args.output,args.token_file,token)


if __name__=='__main__':main()
