"""Read-only physical delivery screen; counterfactual activity is not timing."""
import argparse,gzip,json,hashlib
from collections import Counter,defaultdict
from pathlib import Path
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.io import write_json
from w2w.provenance import revision
from w2w.architecture.serialization import from_record
from w2w.architecture.vertical_streaming import CollectiveResidencyDirectory,VerticalStreamContract


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024**2),b''):h.update(b)
    return h.hexdigest()


def committed_fifo_bound(result):
    """Replay committed miss bytes at unchanged consumer times; precommit omitted."""
    tasks={t['id']:t for t in result['graph']['tasks']};hit={};live=Counter();peak=Counter()
    received=Counter();consumed=Counter();task_peak=Counter();witness={}
    for e in result['events']:
        if e['kind']=='cache_lookup':hit[e['task']]=e['hit']
        key=e.get('task');t=tasks.get(key)
        if not t or not t['stream'] or hit.get(key,False):continue
        tile=t['tile'];s=t['stream']
        if e['kind']=='stream_operand_ready' and e['object_offset']<s['weight_data_bytes']:
            received[key]+=e['bytes'];live[tile]+=e['bytes']
            task_peak[key]=max(task_peak[key],received[key]-consumed[key])
            if live[tile]>peak[tile]:
                peak[tile]=live[tile];witness[tile]=dict(time_ps=e['time_ps'],task=key,bytes=live[tile])
        elif e['kind']=='stream_compute':
            consumed[key]+=e['weight_bytes'];live[tile]-=e['weight_bytes']
            if consumed[key]>received[key] or live[tile]<0:raise ValueError('Miss compute before committed data')
    if any(live.values()) or received!=consumed:raise ValueError('Unconsumed native miss data')
    return dict(peak_by_cluster=dict(peak),maximum_bytes=max(peak.values(),default=0),
        per_task_maximum_bytes=max(task_peak.values(),default=0),witness=witness,
        fp8_miss_bytes=sum(received.values()),
        contract='Lower bound for preserving recorded descriptor commits and compute schedule, ignoring '
            'earlier partial receive writes, scale/X/H storage and native reservations. Not a safe FIFO size '
            'for changed word-level readiness; bypass/staging RAM and early consumption are distinct mechanisms.')


def local_star(graph,stack):
    """Complete charged star protocol, fixed per-edge header/sideband and no X reuse."""
    tasks={t['id']:t for t in graph['tasks']};objects={o['id']:o for o in graph['objects']}
    groups={g.id:g for g in stack.bank_groups};gateways={g.id:g for g in stack.gateways}
    domains={d.id:d for d in stack.dram_domains};clusters={c.id:c for c in stack.compute_clusters}
    incoming=defaultdict(list);outgoing=defaultdict(list)
    for e in graph['data']:incoming[e['consumer']].append(e);outgoing[e['producer']].append(e)
    rows=defaultdict(Counter);blocks=0
    def branch(task):
        obj=objects[task['stream']['weight_object']];group=groups[obj['memory']];g=gateways[group.gateway_id]
        c=clusters[task['tile']]
        if (g.position_um,g.router_id)!=(c.position_um,c.router_id):raise ValueError('Weights are not Gateway-local')
        if len(group.domain_ids)!=8:raise ValueError('Eight physical domains required')
        return g.id,[sum(abs(a-b) for a,b in zip(domains[d].position_um,g.position_um)) for d in group.domain_ids]
    def send(role,payload,length):
        if type(payload) is not int or payload<1:raise ValueError('Explicit finite logical payload required')
        cells=(payload+15)//16+1  # one 128-bit header, then padded 128-bit data words
        r=rows[role];r['messages']+=1;r['sink_payload_bytes']+=payload
        r['payload_byte_um']+=payload*length;r['data_lane_bit_um']+=cells*128*length
        r['cell_bit_um']+=cells*144*length  # 16 bits of separate sideband per word
    for key,gate in tasks.items():
        if not key.endswith('/gate') or not gate['stream']:continue
        prefix=key[:-4];up=tasks[prefix+'up'];down=tasks[prefix+'down'];activation=tasks[prefix+'activation']
        if any(t['stream']['weight_data_bytes']!=524288 or t['stream']['scale_bytes']!=128 for t in (gate,up,down)):
            raise ValueError('Screen requires the frozen 4096x128 FP8/BF16 decode shape')
        if any(t['stream']['macs']!=524288 for t in (gate,up,down)):raise ValueError('Single-token decode only')
        ga,a=branch(gate);ub,b=branch(up);dc,c=branch(down)
        if ga!=dc or activation['tile']!=gate['tile']:raise ValueError('Preserve Gate/H/Down ownership')
        for t,lengths in ((gate,a),(up,b)):
            ins=incoming[t['id']]
            if len(ins)!=1 or ins[0]['size_bytes']!=8192:raise ValueError('Full BF16 X must arrive once per matrix')
            for length in lengths:send('X_fanout',8192,length)
            # Unique scale owner 0 -> root -> other seven slices, on hits and misses.
            send('scale_collect',128,lengths[0])
            for length in lengths[1:]:send('scale_fanout',128,length)
        if (not any(e['consumer']==activation['id'] and e['size_bytes']==512 for e in outgoing[up['id']])
                or not any(e['consumer']==down['id'] and e['size_bytes']==256 for e in outgoing[activation['id']])
                or sum(e['size_bytes'] for e in outgoing[down['id']])!=16384):
            raise ValueError('U/H/Y mathematical interface changed')
        for length in b:send('U_collect',64,length)
        for length in a:send('U_scatter',64,length)
        for length in a:send('H_collect',32,length)
        for length in c:send('H_fanout',256,length)
        for length in c:send('Y_collect',2048,length)
        blocks+=1
    if not blocks:raise ValueError('Complete gated FFN blocks required')
    totals=Counter()
    for r in rows.values():totals.update(r)
    return dict(blocks=blocks,roles={k:dict(v) for k,v in rows.items()},totals=dict(totals),
        wire=dict(bidirectional_data_bit_um=2*128*sum(p.length_um for p in stack.collection_paths),
            bidirectional_sideband_bit_um=2*16*sum(p.length_um for p in stack.collection_paths)),
        contract='Counterfactual routed work, not executed traffic or a lower bound. Fixed star with one '
            '128-bit header and 16 sideband bits per word; no free X reuse, multicast, U fusion or output bypass. '
            'U/global traffic and whole-H barriers remain at current roots. Baseline internal cluster work is '
            'unmeasured and credited zero, favoring the baseline. Local buffer/control/clock costs are additional.')


def observed_case(root,mode):
    source=root/mode;case='up_local_compute';reg=json.loads((source/'registration.json').read_text())
    proof=json.loads((source/'independent-readback.json').read_text());row=proof['cases'][case]
    data=json.load(gzip.open(source/'inputs'/f'{case}.json.gz','rt'))
    if (not proof['passed'] or not row['independent_passed'] or proof['execution_source_commit']!=reg['source_commit']
            or digest(data)!=reg['cases'][case]['input_sha256'] or digest(data['graph'])!=reg['cases'][case]['graph_sha256']):
        raise ValueError('Completed independent input/execution proof required')
    path=source/'cases'/case/'result.json.gz';relative=str(path.relative_to(source));raw=sha(path)
    if raw!=proof['files'][relative]['sha256']:raise ValueError('Audited raw capture changed')
    stack=from_record(data['machine']);paths={p.domain_id:p for p in stack.collection_paths}
    if len(paths)!=len(stack.collection_paths) or set(paths)!={d.id for d in stack.dram_domains}:
        raise ValueError('Unique executed collection path required')
    collection=sum(row['pressure']['domains'][d.id]['atoms']*16*paths[d.id].length_um for d in stack.dram_domains)
    native=sum(row['pressure']['domains'][d.id]['atoms']*16 for d in stack.dram_domains)
    if native!=row['audit']['native_bytes']:raise ValueError('Physical domain bytes differ')
    phase_misses={}
    for phase in ('gate','up','down'):
        size=row['traffic']['operands']['weight/'+phase]['committed_bytes']
        if size%524416:raise ValueError('Uniform original matrix traffic required')
        phase_misses[phase]=size//524416
    if sum(phase_misses.values())*524416!=native:raise ValueError('All native weight traffic must be classified')
    total_read=sum(row['traffic']['actual_stream_weight_read_bytes_by_cluster'].values())
    miss_read=sum(phase_misses.values())*524288
    streams=[t['stream'] for t in data['graph']['tasks'] if t['stream']]
    if any(s['weight_data_bytes']!=524288 or s['scale_bytes']!=128 for s in streams) or total_read!=len(streams)*524288:
        raise ValueError('No inference from nonuniform or incomplete executed weight work')
    local=local_star(data['graph'],stack);cell=local['totals']['cell_bit_um'];memory_bits=collection*8
    fifo=None
    if mode=='cold':
        r=json.load(gzip.open(path,'rt'));fifo=committed_fifo_bound(r);del r
        if fifo['fp8_miss_bytes']!=miss_read:raise ValueError('FIFO replay and audited miss bytes disagree')
    return dict(source_commit=reg['source_commit'],input_sha256=digest(data),raw_sha256=raw,
        proof_sha256=sha(source/'independent-readback.json'),makespan_ps=row['makespan_ps'],
        native_bytes=native,fp8_stream_read_bytes=total_read,fp8_miss_read_bytes=miss_read,
        fp8_hit_read_bytes=total_read-miss_read,maximum_first_use_read_fraction=miss_read/total_read,
        phase_miss_matrices=phase_misses,measured_collection_byte_um=collection,
        measured_global_noc_byte_um=row['pressure']['actual_data_lane_byte_um'],
        proposed_same_miss_native_bytes=native+phase_misses['down']*128,
        local_star=local,committed_fifo_lower_bound=fifo,
        transport_break_even=dict(memory_collection_bit_um=memory_bits,added_local_cell_bit_um=cell,
            logic_to_memory_energy_per_bit_distance_limit=memory_bits/cell,
            inequality='e_logic*added_local_cell_bit_um + incremental_residual_energy < e_memory*collection_bit_um',
            contract='Equal current miss identities only; coefficient ratio bound sets all other increments to zero. '
                'No calibrated energy, EDP, latency or area result. Headers/sideband are paid on logic; array data '
                'collection counts payload only. Controls, padding reads, buffers, shared directory and clocks remain residual.'),
        limits=['Warm consumer FIFO is not reconstructed; traffic comes from hashed completed independent evidence.',
            'First-use SRAM read saving is an upper bound shared by a Gateway-to-PE bypass reference.',
            'The local protocol routes actual frozen workload demands; placement itself is not optimized with future routing.'])


def analyze(root,foil_root):
    cases={m:observed_case(root,m) for m in ('cold','multilayer')}
    proof=json.loads((foil_root/'analysis-final.json').read_text())
    if not proof['passed']:raise ValueError('Completed foil proof required')
    path=foil_root/'cold-r1/cases/up-local-down-prefetch/result.json.gz'
    if sha(path)!=proof['files']['cases/up-local-down-prefetch/result.json.gz']['sha256']:
        raise ValueError('Prefetch FIFO capture changed')
    r=json.load(gzip.open(path,'rt'));prefetch=committed_fifo_bound(r);del r
    return dict(schema='w2w.vertical-delivery-screen.v1',passed=True,analysis_source_commit=revision(),cases=cases,
        prefetch_fifo_lower_bound=prefetch,directory=CollectiveResidencyDirectory().record(),
        readiness_contracts=dict(descriptor_staging=VerticalStreamContract(4096,additional_staging_bytes=4096).record(),
            word_fifo=VerticalStreamContract(32).record()),
        matched_word_readiness=dict(original_whole_matrix_prefix_bytes_per_neighborhood=2*(524288//32//8+8),
            domain_slices_prefix_bytes_per_neighborhood=VerticalStreamContract(32).record()['prefix_bytes_per_neighborhood']),
        verdict='No structural necessity established for 128 tiles. Evaluate Gateway FIFO bypass at matched word readiness, '
            'then compare direct-domain delivery with matched tile resolution and collective residency. Potential independent '
            'advantage is removal of measured memory collection work, conditional on local fabric and residual cost.',
        contract='Saved-evidence analysis and non-executable cost contracts only; no new Native run, parameter sweep or simulated candidate timing.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--co-placement-root',type=Path,required=True)
    p.add_argument('--foil-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=analyze(a.co_placement_root,a.foil_root);write_json(a.output,r)
    print(json.dumps(dict(passed=True,cases={k:dict(memory_byte_um=v['measured_collection_byte_um'],
        local_cell_bit_um=v['local_star']['totals']['cell_bit_um'],break_even=v['transport_break_even']['logic_to_memory_energy_per_bit_distance_limit']) for k,v in r['cases'].items()})))


if __name__=='__main__':main()
