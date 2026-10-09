"""Read the fixed geometry/streaming runs; no simulator execution or new search."""
import argparse
import gzip
import json
from pathlib import Path

from w2w.analysis.moe_layer import digest, file_record, inspect
from w2w.validation.system_execution import audit_system_result


def analyze(source):
    reg=json.loads((source/'registration.json').read_text())
    frozen=json.loads((source/'input.json').read_text())
    if digest(frozen)!=reg['input_sha256']:
        raise ValueError('Registered input changed')
    records={}
    signatures=set()
    proofs={}
    for name in reg['cases']:
        directory=source/'cases'/name
        done=json.loads((directory/'completion.json').read_text())
        summary=json.loads((directory/'summary.json').read_text())
        with gzip.open(directory/'result.json.gz','rt') as f:result=json.load(f)
        if (not done['complete'] or done['source_commit']!=reg['source_commit']
            or done['input_sha256']!=reg['input_sha256'] or result['spec']!=frozen['spec']
            or result['graph']!=frozen['graph'] or result['wafer_machine']!=frozen['physical']
            or done['makespan_ps']!=result['makespan_ps']):
            raise ValueError('Run differs from registered task/machine')
        check=audit_system_result(result)
        if not check['passed'] or check!=result['audit']:
            raise ValueError('Independent event audit differs')
        row=inspect(result,summary)
        signatures.add((row['graph_sha256'],row['logical_read_set_sha256'],
                        digest(row['native_identity']),result['network']['identity']['binary_sha256']))
        native=result['native']
        if (native['streaming']!=(name=='hbm2-stream') or native['pending']
                or native['upstream_pending'] or result['network']['runtime_source']['kind']!='bundled_w2w'):
            raise ValueError('Unexpected backend mode or undrained native state')
        ready={e['request']:e['time_ps'] for e in result['events'] if e['kind']=='native_ready'}
        supply={e['packet'][:-5]:e['time_ps'] for e in result['events'] if e['kind']=='response_first_supply'}
        row['streaming_progress']=dict(supplied_descriptors=len(supply),
            supply_before_full_native=sum(t<ready[k] for k,t in supply.items()))
        if row['streaming_progress']!=summary['streaming_progress']:
            raise ValueError('Streaming summary differs from events')
        row['peak_memory_bytes']=max(row['memory_read_bytes'].values())
        row['native_peak_bandwidth_necessary_bound_us']=row['peak_memory_bytes']/32000
        row['outstanding_peak']=result['outstanding_peak']
        row['mc_peak']=result['mc_peak']
        row['native_last_ready_ps']=max(ready.values())
        row['drained_ps']=result['drained_ps']
        row['wall_seconds']=summary['wall_seconds']
        records[name]=row
        proofs[name]={p:file_record(directory/p) for p in ('result.json.gz','summary.json','completion.json')}
        del result
    if len(signatures)!=1:
        raise ValueError('Cases changed workload, native configuration, or network executable')
    base=records['hbm2-whole']['makespan_us']
    for row in records.values():row['completion_reduction_vs_whole_percent']=100*(1-row['makespan_us']/base)
    physical=frozen['physical']
    # These resources are manufacturing proxies. No area or energy conversion.
    fields=('data_wire_bit_mm','link_register_bits','credit_wire_bit_mm','credit_register_bits')
    return dict(schema='w2w.machine-closure-analysis.v1',source_commit=reg['source_commit'],
        scope=reg['scope'],input_sha256=reg['input_sha256'],machine_sha256=reg['machine_sha256'],
        cases=records,physical_totals={k:sum(p[k] for p in physical['paths']) for k in fields},
        machine_assumptions=physical['assumptions'],raw_result_provenance=proofs,passed=True,
        interpretation='Geometry and native streaming on unchanged HBM2 budget; not high-parallel RWDL or physical calibration')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    r=analyze(args.source)
    args.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:dict(makespan_us=v['makespan_us'],streaming=v['streaming_progress']) for k,v in r['cases'].items()},indent=2))


if __name__=='__main__':main()
