"""Read-only task/operand/service diagnosis from completed physical evidence."""
import argparse,gzip,json
from pathlib import Path
from w2w.analysis.npu_competition import competition
from w2w.analysis.memory_service_causality import explain_pool_window
from w2w.analysis.runtime_windows import audit_window_chain
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control
from w2w.validation.npu_resources import audit_npu_result
from w2w.workloads.moe_trace import file_sha
from w2w.provenance import revision
from w2w.common.io import write_json


def analyze(path,windows=None):
    result=json.load(gzip.open(path,'rt'));rows=[]
    def visit(raw,row):
        ledger=competition(raw)
        projections=[v for k,v in ledger['tasks'].items() if k.endswith(('/gate','/up','/down'))]
        tail=sorted(projections,key=lambda v:v['completed_ps'])[-12:]
        issued={e['task'] for e in raw['events'] if e['kind']=='read_issue'}
        target=next((v['task'] for v in reversed(tail) if v['task'] in issued),None)
        diagnostic=explain_pool_window(raw,target) if target else None
        if diagnostic:
            diagnostic.pop('pool_ownership_witnesses');diagnostic.pop('target_descriptors')
        rows.append(dict(index=row['index'],begin_ps=raw.get('runtime_window_begin_ps',0),end_ps=raw['makespan_ps'],
            clusters=ledger['clusters'],last_projection_pairs=sorted(ledger['projection_pairs'].values(),key=lambda p:p['joint_ready_ps'])[-8:],
            tail_projections=tail,last_projection_with_native_read=diagnostic,scope=ledger['scope']))
    if result.get('schema')=='w2w.runtime-window-summary.v1':
        if windows is None:raise ValueError('Complete window directory required')
        proof=audit_window_chain(result,windows,visit=visit)
    else:
        proof=dict(physical=audit_vertical_result(result),requests=audit_request_control(result),npu=audit_npu_result(result))
        visit(result,dict(index=0))
    return dict(passed=True,analysis_source=revision(),result_sha256=file_sha(path),proof=proof,windows=rows,
        scope='Read-only diagnosis of completed supplied evidence. The input experiment scope is unchanged; directed qualifications do not become complete-request results. No counterfactual hardware performance or calibrated energy/area claim.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--result',type=Path,required=True)
    p.add_argument('--windows',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Preserve existing diagnostic evidence')
    write_json(a.output,analyze(a.result,a.windows))
