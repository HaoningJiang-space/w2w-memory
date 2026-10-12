"""Run only the authorized G3 explanation / row mapping / streaming study."""
import argparse,json,subprocess,sys,time
from pathlib import Path

from w2w.common.io import write_json
from w2w.provenance import revision
from w2w.workloads.moe_trace import file_sha


def accepted(path):
    value=json.loads(path.read_text())
    if value.get('passed') is not True:raise ValueError('Failed ordered prerequisite: '+str(path))
    return value


def run(args):
    root=args.output;root.mkdir(parents=True,exist_ok=False);source=revision();start=time.monotonic();launched=[];completed={}
    stages=('p1','p2a','p2b','p3');through=stages.index(args.through)
    g3=args.finisher/'receipt.json'
    write_json(root/'registration.json',dict(source_commit=source,requested_through=args.through,study=str(args.study),
        G3_receipt=str(g3),scope='Only ordered P1/P2-A/P2-B/P3 work. Original frozen Native runs and held broad G4/G5 controllers remain unchanged. No physical retry, truncated accepted case, uncharged resources or fabricated original-step checkpoint.'))
    def status(state,**fields):write_json(root/'status.json',dict(state=state,source_commit=source,wall_seconds=time.monotonic()-start,
        completed=completed,launched=launched,**fields))
    try:
        while not g3.exists():
            old=json.loads((args.finisher/'status.json').read_text())
            if old.get('state')=='reader_failed':raise ValueError('Original G3 audit failed; do not launch later work')
            status('waiting_G3_audit');time.sleep(30)
        receipt=accepted(g3)
        if not receipt.get('complete_scoped_B1_G3') or not all(receipt['gates'].values()):raise ValueError('Complete G3 audit required')
        for path,sha in receipt['sources'].items():
            if file_sha(Path(path))!=sha:raise ValueError('Accepted G3 files changed')
        if args.reuse_p1:
            p1=accepted(args.reuse_p1);analysis=args.reuse_p1.parent/'analysis.json'
            if p1['G3_receipt_sha256']!=file_sha(g3) or p1['analysis_sha256']!=file_sha(analysis):raise ValueError('Reused P1 is not the accepted original pair')
            p1_path=args.reuse_p1
            completed['p1']=dict(receipt=str(p1_path),sha256=file_sha(p1_path))
        else:p1_path=root/'p1/receipt.json'
        commands=dict(p1=['-m','tools.analyze_phase_split_sources','--study',str(args.study),'--finisher',str(args.finisher),
            '--reference',str(args.reference),'--output',str(root/'p1')],
            p2a=['-m','tools.validate_row_mapping','--output',str(root/'p2a'),'--reference-source',str(args.reference_source),
                '--p1-receipt',str(p1_path),'--booksim-binary',str(args.booksim_binary)],
            p2b=['-m','tools.validate_operand_streaming','--output',str(root/'p2b'),'--p2a-receipt',str(root/'p2a/receipt.json'),
                '--booksim-binary',str(args.booksim_binary)],
            p3=['-m','tools.run_batched_execution','--output',str(root/'p3'),'--study',str(args.study),
                '--p2a-receipt',str(root/'p2a/receipt.json'),'--p2b-receipt',str(root/'p2b/receipt.json'),
                '--booksim-binary',str(args.booksim_binary),'--horizon',args.horizon])
        for stage in stages[:through+1]:
            if stage in completed:continue
            if revision()!=source:raise ValueError('Ordered execution source changed')
            with (root/(stage+'.log')).open('xb') as log:
                process=subprocess.Popen([sys.executable,*commands[stage]],stdout=log,stderr=subprocess.STDOUT)
                launched.append(dict(stage=stage,pid=process.pid,args=commands[stage],source_commit=source));status('running',stage=stage)
                while process.poll() is None:status('running',stage=stage);time.sleep(10)
            if process.returncode:raise RuntimeError(f'{stage} ended with {process.returncode}; preserved, no automatic retry')
            path=root/stage/'receipt.json';accepted(path);completed[stage]=dict(receipt=str(path),sha256=file_sha(path))
        status('complete_requested_scope',through=args.through)
        write_json(root/'receipt.json',dict(passed=True,source_commit=source,completed=completed,G3_receipt_sha256=file_sha(g3),
            complete_all_four_steps=args.through=='p3',horizon=args.horizon,
            scope='Completed only the explicitly recorded ordered horizon; p1-only preparation is not acceptance of later physical stages. No G4/G5 or full Transformer result.'))
    except Exception as error:
        status('failed',reason=str(error),no_automatic_retry=True);raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('output','study','finisher','reference','reference-source','booksim-binary'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--through',choices=('p1','p2a','p2b','p3'),required=True)
    parser.add_argument('--horizon',choices=('selected_windows','complete_request'),default='selected_windows')
    parser.add_argument('--reuse-p1',type=Path)
    run(parser.parse_args())
