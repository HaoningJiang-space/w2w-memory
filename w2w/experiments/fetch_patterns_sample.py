"""Download a bounded, explicitly selected routing sample (CLI compatibility entry).

Reusable HTTP, identity and completed-file resume logic is in
w2w.workloads.patterns_download. No recursive or automatic alternate-host fetch.
"""
import argparse
import json

# Keep historical imports working; new callers use the workload input module.
from w2w.workloads.patterns_download import (
    REPO, OriginBoundAuthorization, fetch, get_bytes,
)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--endpoint',default='https://huggingface.co',
                   help='Explicit HTTPS source; default is the official HF origin')
    p.add_argument('--prefix',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--max-files',type=int,default=2)
    p.add_argument('--max-file-bytes',type=int,default=2*1024**2)
    p.add_argument('--max-total-bytes',type=int,default=4*1024**2)
    p.add_argument('--token-file',help='Optional secret file; official HF host only; never persisted in receipt')
    p.add_argument('--selection',choices=('smallest','seeded'),default='smallest')
    p.add_argument('--seed',type=int,default=0)
    p.add_argument('--resume',action='store_true',help='Reuse hash-verified complete files; not partial-byte resume')
    p.add_argument('--revision',help='Pin a known dataset commit')
    args=p.parse_args()
    receipt=fetch(args.endpoint,args.prefix,args.output,args.max_files,args.max_file_bytes,args.max_total_bytes,args.token_file,
                  args.selection,args.seed,args.resume,args.revision)
    print(json.dumps(receipt))


if __name__=='__main__':main()
