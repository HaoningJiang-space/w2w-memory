"""Audit two narrower C-C runs against completed fixed-service 256 B references."""
import argparse
import json
from pathlib import Path
from w2w.analysis.compute_placement import analyze as analyze_placement
from w2w.analysis.communication_resources import communication_resources,receive_service_work
from w2w.analysis.moe_layer import file_record
from w2w.common.fingerprints import digest_system_v2 as digest
from w2w.validation.communication_budget import cc_width_contract


def analyze(source):
    reg=json.loads((source/'registration.json').read_text());control=reg['communication_reference']
    reference=Path(control['directory']);old_reg=json.loads((reference/'registration.json').read_text())
    if old_reg['source_commit']!=control['source_commit']:raise ValueError('Reference execution identity changed')
    old=analyze_placement(reference);new=analyze_placement(source)
    names={'gather-stream','near-shard-stream'}
    if set(old['cases'])!=names or set(new['cases'])!=names:raise ValueError('Expected only two fixed placement cases')
    rows={};ledgers=[]
    for name in sorted(names):
        a=json.loads((reference/'inputs'/(name+'.json')).read_text())
        b=json.loads((source/'inputs'/(name+'.json')).read_text())
        proof=cc_width_contract(a,b)
        if proof!=control['controls'][name]:raise ValueError('Registered C-C intervention changed')
        x,y=old['cases'][name],new['cases'][name]
        if (x['native_identity']!=y['native_identity'] or x['graph_sha256']!=y['graph_sha256']
                or x['logical_read_set_sha256']!=y['logical_read_set_sha256']
                or x['memory_read_bytes']!=y['memory_read_bytes'] or x['total_compute_busy_ps']!=y['total_compute_busy_ps']
                or x['network_identity']['binary_sha256']!=y['network_identity']['binary_sha256']):
            raise ValueError('Executed native, task, compute or physical read work changed')
        sa=json.loads((reference/'cases'/name/'summary.json').read_text())
        sb=json.loads((source/'cases'/name/'summary.json').read_text())
        if sa['native']['config']!=sb['native']['config']:raise ValueError('Actual native command configuration changed')
        configs=[];topologies=[]
        for root,slots in ((reference,16),(source,32)):
            network=(root/'cases'/name/'network').resolve()
            config=(network/'rapidchiplet/booksim2/src/rc_configs/network.conf').read_text()
            for key,filename in (('trace_file','empty_network_input.json'),('trace_report','trace_report.json')):
                config=config.replace(f'{key} = {network/filename};',f'{key} = <run>/{filename};')
            marker=f'vc_buf_size = {slots};'
            if config.count(marker)!=1:raise ValueError('Native input cell count differs from registered budget')
            configs.append(config.replace(marker,'vc_buf_size = <fixed bytes>;'))
            topologies.append((network/'rapidchiplet/booksim2/src/rc_topologies/network.anynet').read_bytes())
        if configs[0]!=configs[1] or topologies[0]!=topologies[1]:
            raise ValueError('Network control changed routing, timing or another native parameter')
        for summary,record in ((sa,a),(sb,b)):
            nw=summary['network'];sp=record['spec'];compute=record['services']['compute']
            if (nw['identity']['flit_bytes']!=sp['flit_bytes'] or nw['identity']['rx_slots']!=sp['input_buffer_flits']
                    or nw['ni_tx_capacity_bytes_per_node']!=65536
                    or nw['cell_format']['sideband_bits']!=64
                    or summary['sram_read_bytes']!=sa['sram_read_bytes']
                    or summary['sram_read_busy_cycles']!=sa['sram_read_busy_cycles']
                    or compute['external_write_bytes_per_cycle']!=sp['rx_write_bytes_per_cycle']):
                raise ValueError('Endpoint, SRAM or sideband service differs from frozen control')
        write_a,write_b=receive_service_work(a),receive_service_work(b)
        if (write_a['local_cycles_by_class']!=write_b['local_cycles_by_class']
                or write_a['bytes_by_class']!=write_b['bytes_by_class']
                or write_a['total_cycles_by_class']!=sa['network']['rx_write_cycles_by_class']
                or write_b['total_cycles_by_class']!=sb['network']['rx_write_cycles_by_class']):
            raise ValueError('Local DMA service or remote per-cell write work differs from contract')
        cost_a,cost_b=communication_resources(a),communication_resources(b);ledgers.append(digest([cost_a,cost_b]))
        rows[name]=dict(control=proof,reference_makespan_us=x['makespan_us'],candidate_makespan_us=y['makespan_us'],
            completion_increase_percent=100*(y['makespan_us']/x['makespan_us']-1),
            throughput_retained_percent=100*x['makespan_us']/y['makespan_us'],
            absolute_change_us=y['makespan_us']-x['makespan_us'],
            reference_hop_flits=x['audit']['physical_link_flits'],candidate_hop_flits=y['audit']['physical_link_flits'],
            reference_receive_write_ports=x['pressure']['receive_write_ports'],candidate_receive_write_ports=y['pressure']['receive_write_ports'],
            reference_row_totals=x['row_totals'],candidate_row_totals=y['row_totals'],
            reference_last_native_tail_ps=x['native_gap']['final_rw_dl_hb_tail_ps'],
            candidate_last_native_tail_ps=y['native_gap']['final_rw_dl_hb_tail_ps'],
            reference_receive_service_work=write_a,candidate_receive_service_work=write_b,
            reference_resources=cost_a,candidate_resources=cost_b)
    if len(set(ledgers))!=1:raise ValueError('Resource costs depend on architecture placement')
    return dict(schema='w2w.communication-budget-analysis.v1',passed=True,
        source_commit=reg['source_commit'],reference_source_commit=control['source_commit'],cases=rows,
        reference_analysis=old,candidate_analysis=new,
        registration_provenance=dict(reference=file_record(reference/'registration.json'),candidate=file_record(source/'registration.json')),
        interpretation='Only two data widths at one fixed workload/service point; no optimum or calibrated PPA claim')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args();value=analyze(args.source)
    args.output.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    print(json.dumps({n:{k:v for k,v in r.items() if k.endswith('_us') or k.endswith('_percent')}
                      for n,r in value['cases'].items()}))


if __name__=='__main__':main()
