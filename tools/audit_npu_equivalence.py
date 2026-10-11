"""Compare retained cycle/epoch records, verifying only archive pathname normalization."""
import argparse,gzip,json
from pathlib import Path
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control
from w2w.validation.npu_resources import audit_npu_result
from w2w.workloads.moe_trace import file_sha
from w2w.common.io import write_json
from w2w.provenance import revision


def audit(root,execution_commit):
    previous=None;rows=[]
    for kind in ('cycles','epochs'):
        directory=root/f'A16-M1-{kind}';path=directory/'comparison-raw.json.gz'
        r=json.load(gzip.open(path,'rt'));audit_vertical_result(r);audit_request_control(r);audit_npu_result(r)
        if r['npu_execution']['evidence']!=kind:raise ValueError('Wrong retained NPU evidence variant')
        cfg=(directory/'network/network.conf').read_text().replace(str((directory/'network').resolve()),'<ARCHIVE>')
        topology=(directory/'network/network.anynet').read_bytes()
        network_config_sha=file_sha(directory/'network/network.conf')
        if network_config_sha!=r['network']['identity']['config_sha256']:raise ValueError('Raw BookSim config changed')
        comparable=json.loads(json.dumps(r,sort_keys=True).replace(kind+'/','same/'))
        comparable['events']=[e for e in comparable['events'] if e['kind'] not in ('npu_cycle','npu_epoch')]
        comparable.pop('npu_execution');comparable.pop('input_sha256');comparable['network']['identity'].pop('config_sha256')
        if previous is None:previous=comparable;previous_cfg=cfg;previous_topology=topology
        elif comparable!=previous or cfg!=previous_cfg or topology!=previous_topology:
            raise ValueError('Physical result/event/resource/config changed beyond evidence encoding and verified archive paths')
        rows.append(dict(kind=kind,raw_result_sha256=file_sha(path),config_sha256=network_config_sha,
            topology_sha256=file_sha(directory/'network/network.anynet'),makespan_ps=r['makespan_ps']))
    return dict(passed=True,execution_source_commit=execution_commit,analysis_source_commit=revision(),variants=rows,
        scope='Full Qwen3 Gate projection Native DRAM/NoC/resource/task event equivalence and identical integer-ps completion. '
            'NPU internal cycle versus hashed-program interval evidence differs by design. Config hash differs only in independently verified archive path strings; original failed checks retained.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--execution-commit',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=audit(a.root,a.execution_commit);write_json(a.output,r);print(json.dumps(r))
