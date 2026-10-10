"""Independent raw audit of the frozen operand-aware vertical access pair."""
import argparse,gzip,json,hashlib
from pathlib import Path
from w2w.common.io import write_json
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.architecture.serialization import from_record
from w2w.architecture.resources import matched_vertical_budget
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control
from w2w.provenance import revision


def cuts(result):
    routers={r['id']:r['position_um'] for r in result['spec']['routers']}
    rows={};period=result['spec']['noc_period_ps'];flit=result['spec']['flit_bytes']
    for axis,name in enumerate(('x-midline','y-midline')):
        links=[l for l in result['spec']['links'] if (routers[l['src']][axis]<0)!=(routers[l['dst']][axis]<0)]
        count=sum(result['network']['link_flits'].get(l['id'],0) for l in links)
        rows[name]=dict(directed_channels=len(links),executed_macro_cells=count,executed_data_lane_bytes=count*flit,
            capacity_bytes_per_ps=len(links)*flit/period,
            executed_volume_bound_ps=(count*period+len(links)-1)//len(links),
            scope='actual macro-cell traffic across both directions; independent directed channel capacity; includes headers/packing, sideband separate; not an optimal-placement lower bound')
    return rows


def analyze(source):
    reg=json.loads((source/'registration.json').read_text());inputs={};rows={};files={}
    if reg['schema']!='w2w.operand-access-pair.v1' or set(reg['cases'])!={'central-plus','distributed'}:
        raise ValueError('Incomplete operand-aware access pair')
    for case,identity in reg['cases'].items():
        data=json.loads((source/'inputs'/f'{case}.json').read_text());path=source/'cases'/case
        row=json.loads((path/'completion.json').read_text())
        with gzip.open(path/'result.json.gz','rt') as f:r=json.load(f)
        if (not row['complete'] or digest(data)!=identity['input_sha256'] or row['input_sha256']!=identity['input_sha256'] or
            row['source_commit']!=reg['source_commit'] or r['source_commit']!=reg['source_commit'] or
            r['spec']['stack']!=data['machine'] or r['graph']!=data['graph'] or r['makespan_ps']!=row['makespan_ps'] or
            r['operand_readiness']!=row['operand_readiness'] or r['operand_readiness']['policy']!='contiguous_prefix' or
            r['native']['config_sha256']!=row['native_config_sha256'] or r['network']['identity']['binary_sha256']!=row['booksim_sha256'] or
            r['native']['bridge_sha256']!=row['bridge_sha256']):raise ValueError('Paired source/input/execution identity changed')
        a=audit_vertical_result(r);b=audit_request_control(r);arbiter=r['network']['source_arbiter']
        if (a!=row['audit'] or b!=row['control_audit'] or not r['native']['request_control']['enabled'] or
            r['compute_execution']['contexts_per_cluster']!=data['compute_contexts'] or
            arbiter['additional_metadata_bits']!=data['selector_bits'] or arbiter['routers']!=list(data['network_policy']['ready_router_ids']) or
            sum(e['macs'] for e in r['events'] if e['kind']=='stream_compute')!=data['metadata']['macs'] or 'weight_cache' in r):
            raise ValueError('Paired compute, control, selector or conservation contract changed')
        period=r['spec']['noc_period_ps'];pressure=r['network']['final']['source_pressure']
        rows[case]=dict(**row,independent_passed=True,cut_bounds=cuts(r),necessary_service_bounds_ps=dict(
            native_interface=max(r['native']['channel_atoms'].values())*r['native']['tck_ps'],
            busiest_executed_channel=max(r['network']['link_flits'].values(),default=0)*period,
            busiest_rx_write=max(r['network']['rx_write_cycles'].values(),default=0)*period,
            busiest_arithmetic=max(r['compute_busy_ps'].values(),default=0)),
            source_pressure={k:v for k,v in pressure.items() if not k.endswith('_by_message')},
            domain_atoms=r['native']['channel_atoms'],native_reservation_peak_atoms=r['native']['reservation_peak_atoms'],
            gateway_queue_peak_bytes=r['native']['gateway_queue_peak_bytes'],request_control=r['native']['request_control'])
        inputs[case]=data
        for file in (source/'inputs'/f'{case}.json',path/'completion.json',path/'result.json.gz'):
            h=hashlib.sha256()
            with file.open('rb') as f:
                for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
            files[str(file.relative_to(source))]=dict(bytes=file.stat().st_size,sha256=h.hexdigest())
    a,b=(inputs[k] for k in ('central-plus','distributed'))
    for key in ('logical','weights','placement','graph','metadata','operand_readiness','request_control','refresh','compute_contexts','cache','network_policy','selector_bits'):
        if a[key]!=b[key]:raise ValueError('Access pair changed work or another execution policy')
    for field in ('native_config_sha256','booksim_sha256','bridge_sha256'):
        if rows['central-plus'][field]!=rows['distributed'][field]:raise ValueError('Native tools or service changed')
    if rows['central-plus']['audit']['native_bytes']!=rows['distributed']['audit']['native_bytes']:
        raise ValueError('Cold paired access changed required read bytes')
    proof=matched_vertical_budget(from_record(a['machine']),from_record(b['machine']))
    if proof!=reg['budget_match']:raise ValueError('Registered physical budget changed')
    return dict(schema='w2w.operand-access-analysis.v1',passed=True,execution_source_commit=reg['source_commit'],analysis_source_commit=revision(),
        cases=rows,budget_match=proof,completion_reduction_percent=100*(1-rows['distributed']['makespan_ps']/rows['central-plus']['makespan_ps']),files=files,
        limits=['one cold routed FFN, not steady-state or complete Transformer','ideal global receive reservation',
            'declared array timing, aggregate PE/SRAM banking and resource proxies; not calibrated silicon/PPA',
            'ready-aware priority is admission order among ready, not every optimized central microarchitecture',
            'service/cut bounds and pressure counters overlap; they are not a total stall decomposition'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();r=analyze(args.source);write_json(args.output,r)
    print(json.dumps(dict(passed=True,makespan_ps={k:v['makespan_ps'] for k,v in r['cases'].items()},completion_reduction_percent=r['completion_reduction_percent'])))


if __name__=='__main__':main()
