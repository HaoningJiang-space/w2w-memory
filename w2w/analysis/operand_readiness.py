"""Re-audit a completed readiness probe; never execute or repair missing cases."""
import argparse,gzip,json
from pathlib import Path
from w2w.common.io import write_json
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control


def analyze(source):
    report=json.loads((source/'analysis.json').read_text());proof={};inputs={};graph=None
    expected={o+'-'+p for o in ('central','distributed') for p in ('byte_count','contiguous_prefix')}
    if report['schema']!='w2w.operand-readiness-probe.v1' or set(report['cases'])!=expected:
        raise ValueError('Incomplete or incompatible readiness probe')
    for case,summary in report['cases'].items():
        directory=source/case;data=json.loads((directory/'input.json').read_text())
        completion=json.loads((directory/'completion.json').read_text())
        result=json.load(gzip.open(directory/'result.json.gz','rt'))
        if (completion!=summary or summary['source_commit']!=report['source_commit']
                or digest(data)!=summary['input_sha256'] or result['graph']!=data['graph']
                or result['spec']['stack']!=data['machine'] or result['makespan_ps']!=summary['makespan_ps']
                or result['operand_readiness']!=summary['operand_readiness']
                or result['native']['config_sha256']!=summary['native_config_sha256']
                or result['network']['identity']['binary_sha256']!=summary['binary_sha256']
                or sum(result['compute_busy_ps'].values())!=summary['arithmetic_busy_ps']
                or result['sram_peak_bytes']!=summary['sram_peak_bytes']
                or sum(result['network']['link_flits'].values())!=summary['hop_flits']
                or result['native']['request_control']['enabled']!=data['request_control']
                or result['operand_readiness']['policy']!=data['operand_readiness']
                or result['compute_execution']['contexts_per_cluster']!=data['compute_contexts']):
            raise ValueError('Readiness execution/completion identity changed')
        if graph is not None and graph!=result['graph']:raise ValueError('Work/placement changed')
        graph=result['graph'];audit=audit_vertical_result(result);control=audit_request_control(result)
        if audit!=summary['audit'] or control!=summary['control_audit']:
            raise ValueError('Independent readiness conservation differs')
        if sum(e['macs'] for e in result['events'] if e['kind']=='stream_compute')!=summary['macs']:
            raise ValueError('Readiness intervention changed arithmetic work')
        proof[case]=dict(passed=True,audit=audit,control_audit=control);inputs[case]=data
    for organization in ('central','distributed'):
        a,b=(organization+'-'+p for p in ('byte_count','contiguous_prefix'))
        if {k:v for k,v in inputs[a].items() if k!='operand_readiness'}!={k:v for k,v in inputs[b].items() if k!='operand_readiness'}:
            raise ValueError('Readiness intervention changed another input')
        for key in ('native_config_sha256','binary_sha256','macs','vector_ops'):
            if report['cases'][a][key]!=report['cases'][b][key]:raise ValueError('Native/compute service changed')
        delta=report['cases'][b]['makespan_ps']-report['cases'][a]['makespan_ps']
        if delta!=report['changes'][organization]['delta_ps']:raise ValueError('Reported completion delta differs')
    return dict(schema='w2w.operand-readiness-audit.v1',passed=True,
        execution_source_commit=report['source_commit'],cases=proof,changes=report['changes'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    report=analyze(args.source);write_json(args.output,report)
    print(json.dumps(dict(passed=True,changes=report['changes'])))

if __name__=='__main__':main()
