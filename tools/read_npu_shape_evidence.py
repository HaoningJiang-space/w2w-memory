"""Re-read existing 36 resident and 36 cold full-shape physical microkernels."""
import argparse,gzip,json,time
from collections import Counter
from pathlib import Path

from w2w.validation.npu_resources import audit_npu_result
from w2w.validation.request_control import audit_request_control
from w2w.architecture.npu_profile import reference_profile
from w2w.system.npu_kernel import program
from w2w.workloads.moe_trace import file_sha
from w2w.provenance import revision
from w2w.common.io import write_json


def run(resident,cold,reference,output):
    begin=time.monotonic();prior=json.loads(reference.read_text())
    if prior.get('passed') is not True:raise ValueError('Accepted independent shape reference required')
    refs={(r['array_size'],r['M'],r['phase']):r for r in prior['kernels']}
    wanted={(a,m,k) for a in (16,32) for m in (1,2,4,8,16,32) for k in ('gate','up','down')}
    if set(refs)!=wanted:raise ValueError('Independent reference lacks the complete 36-shape grid')
    output.mkdir(parents=True,exist_ok=False);rows=[];sources={str(reference):file_sha(reference)}
    for root,mode in ((resident,'compute'),(cold,'stream')):
        receipt=root/'receipt.json';r=json.loads(receipt.read_text());sources[str(receipt)]=file_sha(receipt)
        if r.get('passed') is not True or r['mode']!=mode or {(x['array'],x['M'],x['kind']) for x in r['rows']}!=wanted or len(r['rows'])!=36:
            raise ValueError('Physical receipt lacks the complete grid')
        for row in r['rows']:
            path=root/row['file']
            if file_sha(path)!=row['sha256']:raise ValueError('Original physical microkernel changed')
            raw=json.load(gzip.open(path,'rt'));proof=audit_npu_result(raw);audit_request_control(raw)
            npu=raw['npu_execution'];key=next(iter(npu['kernels']));kernel=npu['kernels'][key];plan=npu['plans'][key]
            expected=refs[row['array'],row['M'],row['kind']];profile=reference_profile(row['array'])
            if len(npu['kernels'])!=1 or (kernel['M'],kernel['N'],kernel['K'])!=(row['M'],row['N'],row['K']):
                raise ValueError('Actual kernel shape differs from registered physical grid')
            if plan!=expected['plan'] or program(row['M'],row['N'],row['K'],'FP8_E4M3FN',profile)[1]!=plan:
                raise ValueError('Physical or default program differs from independent full-shape reference')
            if raw['makespan_ps']!=row['makespan_ps'] or proof['macs']!=row['M']*row['N']*row['K']:
                raise ValueError('Observed physical shape/time/MAC work changed')
            phases=Counter(e['phase'] for e in raw['events'] if e['kind']=='npu_cycle')
            native=row['audit']['native_bytes']
            if native!=(0 if mode=='compute' else row['N']*row['K']+4*row['N']*row['K']//16384):
                raise ValueError('Resident/cold weight-byte boundary changed')
            task=next(t for t in raw['graph']['tasks'] if t['id']==key)
            epochs=[e for e in raw['events'] if e['kind']=='npu_epoch' and e['task']==key]
            array_start=min(e['time_ps'] for e in raw['events'] if e['kind'] in ('npu_epoch','npu_cycle') and e['task']==key)
            end=raw['tasks'][key]['finish_ps']
            if end-array_start!=plan['cycles']*profile.period_ps:raise ValueError('Actual array execution interval did not close')
            rows.append(dict(array_size=row['array'],arrays=profile.arrays,M=row['M'],N=row['N'],K=row['K'],kind=row['kind'],mode=mode,
                macs=proof['macs'],physical_completion_ps=raw['makespan_ps'],array_start_ps=array_start,array_end_ps=end,
                observed_array_cycles=proof['array_service_cycles'],array_core_cycles=plan['array_cycles'],
                modeled_bank_stall_cycles=plan['bank_stall_cycles'],array_service_efficiency=proof['macs']/(16384*proof['array_service_cycles']),
                actual_service=plan['service'],paid_task_scratch_bytes=task['scratch_bytes'],sram_peak_bytes=raw['sram_peak_bytes'],
                native_bytes=native,program_sha256=plan['program_sha256'],physical_result_sha256=row['sha256'],
                event_mode='epochs' if epochs else 'cycles',proof=proof))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(12,3.7),constrained_layout=True)
    for a in (16,32):
        for kind in ('gate','down'):
            selected=[r for r in rows if r['array_size']==a and r['kind']==kind and r['mode']=='compute']
            cold_rows=[r for r in rows if r['array_size']==a and r['kind']==kind and r['mode']=='stream']
            label=f'{a}×{a}, {kind}';x=[r['M'] for r in selected]
            axes[0].plot(x,[r['observed_array_cycles'] for r in selected],marker='o',label=label)
            axes[1].plot(x,[100*r['array_service_efficiency'] for r in selected],marker='o')
            axes[2].plot(x,[r['physical_completion_ps']/1e6 for r in cold_rows],marker='o')
    axes[0].set(xlabel='Actual M',ylabel='Observed array service cycles',title='Resident full-shape physical kernels');axes[0].legend(fontsize=7)
    axes[1].set(xlabel='Actual M',ylabel='Useful MAC / reserved peak (%)',title='Execution-model efficiency')
    axes[2].set(xlabel='Actual M',ylabel='Cold physical completion (µs)',title='Native delivery then complete-operand OS')
    fig.savefig(output/'physical-shapes.png',dpi=180);plt.close(fig)
    value=dict(passed=True,analysis_source=revision(),sources=sources,cases=rows,physical_cases=72,
        array_organizations=[dict(rows=a,columns=a,arrays=16384//(a*a),macs_per_cycle=16384,sram_bytes_per_cluster=192*1024**2,cache_bytes_per_cluster=184*1024**2) for a in (16,32)],
        reference_commit=prior['reference_commit'],figure_sha256=file_sha(output/'physical-shapes.png'),wall_seconds=time.monotonic()-begin,
        scope='Read-only current NPU/request audits of 72 existing full H/I physical microkernels and exact independent/default program comparison; no new experiments. Observed array intervals and SRAM/partial work close actual event grants. Both organizations retain the same total MAC/SRAM budgets. Cold mode pays Native delivery before complete-operand output-stationary acquisition; no streaming-overlap, optimal mapping or silicon-calibration claim. These standalone shapes are distinct from the nine context projection-shard M/N/K tuples and from captured application timing.')
    write_json(output/'receipt.json',value);print(json.dumps(dict(passed=True,cases=len(rows),wall_seconds=value['wall_seconds'])),flush=True)
    return value


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('resident','cold','reference','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.resident,a.cold,a.reference,a.output)
