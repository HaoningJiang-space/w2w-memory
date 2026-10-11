"""Work/communication bounds, not predicted timing or hardware PPA."""
from collections import Counter
from fractions import Fraction
from math import ceil


def domain_organization_bounds(logical, specification, catalog):
    h,_,width,_,_=logical.shape
    per_domain=Counter();phase=Counter();native_bytes=0;scale_exchange=0;matrix_counts=Counter()
    for op in logical.operations:
        if op.kind!='gemm':continue
        if len(op.weight_tensors)!=1:raise ValueError('One canonical matrix per projection')
        name=op.weight_tensors[0];m=catalog['matrices'][name];p=name.rsplit('/',1)[-1]
        matrix_counts[p]+=1
        for s in m['slices']:
            size=s['data_bytes']+s['scale_storage_bytes']
            per_domain[s['domain_id']]+=size;native_bytes+=size
            scale_exchange+=4*sum(owner!=s['domain_id'] for owner in s['scale_owners'])
        phase[p]+=op.macs
    period=specification.native_period_ps
    native_total_bits=sum(t.hb_data_bits for t in specification.tiles)
    native_lb=ceil(Fraction(native_bytes*8*period,native_total_bits))
    busiest=ceil(Fraction(max(per_domain.values(),default=0)*period,16))
    block_count=matrix_counts['gate']
    if matrix_counts['up']!=block_count or matrix_counts['down']!=block_count:
        raise ValueError('Complete gated FFN projections required')
    routed=sum(len(o.token_ids) for o in logical.operations if o.kind=='gemm' and o.id.endswith('/gate'))
    representative=next(m for name,m in catalog['matrices'].items() if name.endswith('/gate'))
    gate_max=max(s['data_bytes']+s['scale_storage_bytes'] for s in representative['slices'])
    down=next(m for name,m in catalog['matrices'].items() if name.endswith('/down'))
    down_max=max(s['data_bytes']+s['scale_storage_bytes'] for s in down['slices'])
    return dict(schema='w2w.domain-organization-bounds.v1',cold_native_bytes=native_bytes,
        native_total_work_lower_bound_ps=native_lb,native_max_domain_work_lower_bound_ps=busiest,
        native_peak_bytes_per_ns=float(Fraction(native_total_bits*1000,8*period)),
        old_gateway_peak_bytes_per_ns=specification.baseline_gateway_bytes_per_ns,
        gate_domain_payload_time_ps=ceil(Fraction(gate_max*period,16)),
        down_domain_payload_time_ps=ceil(Fraction(down_max*period,16)),
        per_domain_cold_bytes=dict(per_domain),scale_remote_payload_bytes=scale_exchange,
        original_matrix_counts=dict(matrix_counts),macs_by_phase=dict(phase),
        activation_sink_bytes=dict(
            whole_matrix_X=2*routed*h*2,domain_X=2*routed*h*2*8,
            whole_matrix_H=routed*width*2,domain_H=routed*width*2*8,
            U_exchange=routed*width*4,block_down_output=routed*h*4),
        per_token_state=dict(X_copies_across_gate_up_tiles=2*8*h*2,
            G_U_elements_total=2*width*4,H_copies_across_down_tiles=8*width*2,
            down_accumulator_per_tile=(h//8)*4,down_accumulator_total=h*4),
        whole_H_down_prefetch_buffer_per_tile=h//8*width,
        whole_H_down_prefetch_buffer_total=h*width,
        retained_slice_scaling='For identical lockstep references and proportional sizes, C_i=C/8 and W_i=W/8 '
            'give the same collective resident matrix count as a C-sized whole-matrix cache. Original scale ownership/padding '
            'can make one domain slightly tighter; neither slicing nor more tag tables pools capacity.',
        readiness='Balanced 16-row gate/up slices each take a full domain matrix interval. All eight slices finishing together '
            'does not create 128->16 stage pipelining. Earlier per-row outputs form strided sets across tiles; consuming them '
            'in Down needs a separate layout/readiness/FP32 accumulation-order contract.',
        contract='Cold necessary-work bounds omit startup, ACT/PRE/refresh, control serialization, local fanout, FIFO backpressure, '
            'cache, compute dependencies and shared scheduling. Sink bytes are logical replicas, not multicast edge traffic. '
            'Output slices concatenate within a block; ordered block/partition accumulation still applies.')
