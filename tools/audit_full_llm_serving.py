"""Read completed serving evidence with the current physical-notice binding audit."""
import argparse,json
from pathlib import Path
from w2w.validation.llm_context import audit_serving
from w2w.workloads.moe_trace import file_sha
from w2w.provenance import revision
from w2w.common.io import write_json


def run(root,output):
    if output.exists():raise ValueError('Keep prior serving readback')
    full=json.loads((root/'serving-results.json').read_text())
    if full.get('passed') is not True:raise ValueError('Complete accepted serving execution required')
    reg=json.loads((root/'registration.json').read_text());plan=json.loads((root/'deployment.json').read_text())
    events=json.loads((root/'link-evidence.json').read_text())['events']
    proof=audit_serving(root,reg,plan,full['requests'],events)
    write_json(output,dict(passed=True,analysis_source=revision(),execution_source=full['source_commit'],proof=proof,
        sources={name:file_sha(root/name) for name in ('registration.json','deployment.json','serving-results.json','link-evidence.json')},
        scope='Current reader binds every complete physical stage window, original input ticket, output ownership fence and paid transfer. Conditional routing replay, not numerical Qwen generation or calibrated PPA.'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.root,a.output)
