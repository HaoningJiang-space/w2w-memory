"""Re-audit saved equal-byte domain probes without executing memory or network."""
import argparse,gzip,json,hashlib
from pathlib import Path
from w2w.common.io import write_json
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control
from w2w.validation.rwdl_commands import audit_rwdl_commands
from w2w.provenance import revision


def analyze(source):
    report=json.loads((source/'analysis.json').read_text());proof={};files={};machine=None;configs=[]
    if report['schema']!='w2w.rwdl-domain-probe.v1' or set(report['cases'])!={'uniform-eight','hot-one'}:
        raise ValueError('Incomplete domain service comparison')
    for case,row in report['cases'].items():
        directory=source/case;data=json.loads((directory/'input.json').read_text())
        completion=json.loads((directory/'completion.json').read_text())
        with gzip.open(directory/'result.json.gz','rt') as f:r=json.load(f)
        if (completion!=row or row['source_commit']!=report['source_commit'] or digest(data)!=row['input_sha256'] or
            r['spec']['stack']!=data['machine'] or r['graph']!=data['graph'] or r['makespan_ps']!=row['makespan_ps'] or
            r['native']['config_sha256']!=row['native_config_sha256'] or r['native']['bridge_sha256']!=row['bridge_sha256'] or
            r['network']['identity']['binary_sha256']!=row['booksim_sha256']):
            raise ValueError('Frozen domain probe identity changed')
        if machine is not None and machine!=data['machine']:raise ValueError('Domain intervention changed physical machine')
        machine=data['machine'];config=r['native']['config']
        for controller in config['memory_system']['controllers']:
            for plugin in controller['controller_plugins']:plugin.pop('path',None)
        configs.append(config)
        a=audit_vertical_result(r);b=audit_request_control(r);c=audit_rwdl_commands(r,directory/'commands.csv')
        if (a!=row['audit'] or b!=row['control_audit'] or c!=row['command_audit'] or
            a['native_bytes']!=data['payload_bytes'] or c['active_read_domains']!=(8 if case=='uniform-eight' else 1)):
            raise ValueError('Independent service audits differ')
        proof[case]=dict(passed=True,makespan_ps=r['makespan_ps'],audit=a,control_audit=b,command_audit=c)
        for path in (directory/'input.json',directory/'completion.json',directory/'result.json.gz',*directory.glob('commands.csv.ch*')):
            files[str(path.relative_to(source))]=dict(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    if configs[0]!=configs[1] or digest(configs[0])!=report['matched_native_service_sha256']:
        raise ValueError('Domain service config changed beyond trace destinations')
    ratio=proof['hot-one']['makespan_ps']/proof['uniform-eight']['makespan_ps']
    if ratio!=report['hot_over_uniform_time']:raise ValueError('Reported domain ratio differs')
    return dict(schema='w2w.rwdl-domain-audit.v1',passed=True,execution_source_commit=report['source_commit'],
        analysis_source_commit=revision(),cases=proof,hot_over_uniform_time=ratio,files=files,
        limits=report['limits'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();r=analyze(args.source);write_json(args.output,r)
    print(json.dumps(dict(passed=True,hot_over_uniform_time=r['hot_over_uniform_time'])))


if __name__=='__main__':main()
