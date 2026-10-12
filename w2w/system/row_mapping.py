"""Opt-in paid row-group mapping on the unchanged aggregate NPU resources.

Each physical 16x16 array can expose four 4x16 or two 8x16 OS groups.
Groups have independent weight injection, bounded input broadcast and original
output-interleaved SRAM banks. Configuration, scale routing and extra word
buffers are explicit costs. This is a candidate interface, not calibrated RTL.
"""
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from functools import lru_cache
from math import ceil

from w2w.common.fingerprints import digest_read_v1 as digest
from .npu_kernel import ArrayTile, NPUInstruction, NPUKernelModel, _core_macs, array_tiles, program


@lru_cache(maxsize=64)
def best_os(M,N,K,dtype,p):
    if dtype!='FP8_E4M3FN' or (N,K) not in ((128,4096),(4096,128)):
        return program(M,N,K,dtype,p)
    choices=[program(M,N,K,dtype,p)]
    for split in range(1,K//128+1):
        if K%split or K//split%128:continue
        if split>1 and M*N>p.macs_per_cycle:continue
        choices.append(program(M,N,K,dtype,p,k_partitions=split))
    return min(choices,key=lambda item:(item[1]['cycles'],item[1]['scratch_bytes'],item[1]['k_partitions']))


def row_groups(M,N,K,p,fold):
    if (p.rows,p.columns,p.arrays)!=(16,16,64) or fold not in (2,4) or M>p.rows//fold:
        raise ValueError('Declared two/four row groups on the reference array required')
    base,split=array_tiles(M,N,K,p)
    waves=[]
    if (N,K)==(128,4096):
        mode='k_fold'
        for wave in base:
            groups=[]
            for array,tile in enumerate(wave):
                if tile.K%fold or tile.K//fold%128:raise ValueError('Row K cuts break original scales')
                for q in range(fold):
                    groups.append(dict(m=tile.m,n=tile.n,k=tile.k+q*tile.K//fold,
                        M=tile.M,N=tile.N,K=tile.K//fold,array=array,row_group=q,start_tick=q))
            waves.append(groups)
        split*=fold
    elif (N,K)==(4096,128):
        mode='n_fold';tiles=[t for wave in base for t in wave]
        for offset in range(0,len(tiles),p.arrays*fold):
            chunk=tiles[offset:offset+p.arrays*fold];groups=[]
            # Group-major N assignment and one-cycle phase skew avoid aligning
            # all folded word refills at the same output bank. Actual bank
            # arbitration still decides whether a tick stalls.
            for index,tile in enumerate(chunk):
                q,array=divmod(index,p.arrays)
                groups.append(dict(**asdict(tile),array=array,row_group=q,start_tick=q))
            waves.append(groups)
    else:raise ValueError('Only actual lowered expert shapes are registered')
    return tuple(tuple(g for g in wave) for wave in waves),split,mode


@lru_cache(maxsize=64)
def folded_program(M,N,K,dtype,p,fold):
    if dtype!='FP8_E4M3FN':raise ValueError('Folded reference preserves original FP8 scale groups')
    waves,split,mode=row_groups(M,N,K,p,fold);group_rows=p.rows//fold;code=[]
    scales=4*ceil(N/128)*ceil(K/128)
    configuration_bytes=p.arrays*fold*32
    scale_register_bytes=max(sum(ceil(g['K']/128)*4 for g in w) for w in waves)
    code.append(NPUInstruction('scale_load',-1,0,scale_sram_bytes=scales))
    for wave_id,groups in enumerate(waves):
        code.append(NPUInstruction('row_config_read',wave_id,0,activation_sram_bytes=configuration_bytes,
            bank_peak_activation_bytes=ceil(configuration_bytes/p.banks/p.word_bytes)*p.word_bytes))
        code.append(NPUInstruction('row_config_latch',wave_id,0,vector_ops=len(groups)))
        route_bytes=sum(ceil(g['K']/128)*4 for g in groups)
        code.append(NPUInstruction('row_scale_route',wave_id,0,scale_sram_bytes=route_bytes,
            vector_ops=route_bytes//4,bank_peak_weight_bytes=ceil(route_bytes/p.banks/p.word_bytes)*p.word_bytes))
        cache={};duration=max(g['start_tick']+g['K']+group_rows+p.columns-2 for g in groups)
        for tick in range(duration):
            loads=[];broadcast=defaultdict(list);macs=dequant=delivery=0
            for g in groups:
                local=tick-g['start_tick'];tile=ArrayTile(*(g[f] for f in ('m','n','k','M','N','K')))
                if local<0:continue
                macs+=_core_macs(tile,local)
                for c in range(g['N']):
                    k=local-c
                    if not 0<=k<g['K']:continue
                    dequant+=1;word=(g['k']+k)//p.word_bytes
                    identity=('w',g['array'],g['row_group'],c)
                    if cache.get(identity)!=word:loads.append(('w',(g['n']+c)%p.banks,identity,word))
                for row in range(g['M']):
                    k=local-row
                    if not 0<=k<g['K']:continue
                    delivery+=2;word=(g['k']+k)*2//p.word_bytes
                    identity=('x',g['array'],g['row_group'],row)
                    if cache.get(identity)!=word:broadcast[g['m']+row,word].append((identity,word))
            for (m,word),receivers in broadcast.items():
                for offset in range(0,len(receivers),p.input_broadcast_fanout):
                    loads.append(('x',(m+word)%p.banks,tuple(receivers[offset:offset+p.input_broadcast_fanout]),word))
            while True:
                used=Counter();live=Counter();pending=[]
                for kind,bank,identity,word in loads:
                    limit=p.weight_read_bytes_per_cycle if kind=='w' else p.activation_read_bytes_per_cycle
                    if live[kind,bank]+p.word_bytes>p.bank_port_bytes_per_cycle or used[kind]+p.word_bytes>limit:
                        pending.append((kind,bank,identity,word));continue
                    live[kind,bank]+=p.word_bytes;used[kind]+=p.word_bytes
                    if kind=='w':cache[identity]=word
                    else:
                        for receiver,value in identity:cache[receiver]=value
                if loads and not used:raise ValueError('A finite bank cannot service one word')
                fields=dict(weight_sram_bytes=used['w'],activation_sram_bytes=used['x'],
                    bank_peak_weight_bytes=max((v for (kind,_),v in live.items() if kind=='w'),default=0),
                    bank_peak_activation_bytes=max((v for (kind,_),v in live.items() if kind=='x'),default=0))
                if pending:
                    code.append(NPUInstruction('array_input_stall',wave_id,tick,bank_stall=True,**fields))
                    loads=pending;continue
                if macs>p.macs_per_cycle or dequant>p.vector_ops_per_cycle or delivery>p.activation_read_bytes_per_cycle:
                    raise ValueError('Folded MAC/conversion/input grant exceeds original resources')
                code.append(NPUInstruction('array',wave_id,tick,macs=macs,vector_ops=dequant,
                    accumulator_register_bytes=macs*8,activation_delivery_bytes=delivery,**fields))
                break
        remaining=sum(g['M']*g['N']*4 for g in groups)
        while remaining:
            count=min(remaining,p.output_write_bytes_per_cycle,p.banks*p.bank_port_bytes_per_cycle)
            code.append(NPUInstruction('partial_store',wave_id,duration,output_sram_bytes=count));remaining-=count
    if split>1:
        if M*N>p.macs_per_cycle:raise ValueError('Reduction exceeds existing accumulator registers')
        for part in range(split):
            remaining=M*N;tick=0
            while remaining:
                count=min(remaining,p.activation_read_bytes_per_cycle//4,p.banks*p.bank_port_bytes_per_cycle//4,
                    p.vector_ops_per_cycle if part else remaining)
                code.append(NPUInstruction('ordered_k_load' if part==0 else 'ordered_k_add',len(waves),tick,
                    activation_sram_bytes=4*count,vector_ops=count if part else 0,
                    accumulator_register_bytes=(8 if part else 4)*count))
                remaining-=count;tick+=1
        remaining=M*N*4;tick=0
        while remaining:
            count=min(remaining,p.output_write_bytes_per_cycle,p.banks*p.bank_port_bytes_per_cycle)
            code.append(NPUInstruction('ordered_k_final_store',len(waves),tick,output_sram_bytes=count,
                accumulator_register_bytes=count));remaining-=count;tick+=1
    if sum(i.macs for i in code)!=M*N*K:raise ValueError('Folded mathematical work changed')
    fields=('weight_sram_bytes','scale_sram_bytes','activation_sram_bytes','output_sram_bytes','vector_ops',
        'accumulator_register_bytes','activation_delivery_bytes')
    word_buffers=p.arrays*(p.rows+p.columns*fold)*p.word_bytes
    context=p.arrays*(p.rows*p.columns*4+32)+word_buffers+configuration_bytes+scale_register_bytes
    plan=dict(M=M,N=N,K=K,weight_dtype=dtype,k_partitions=split,waves=[list(w) for w in waves],
        cycles=len(code),array_cycles=sum(i.phase=='array' for i in code),bank_stall_cycles=sum(i.bank_stall for i in code),
        macs=M*N*K,scratch_bytes=context+M*N*split*4,mac_utilization=M*N*K/(p.macs_per_cycle*len(code)),
        service={f:sum(getattr(i,f) for i in code) for f in fields},program_sha256=digest([asdict(i) for i in code]),
        peak_service={f:max(getattr(i,f) for i in code) for f in ('macs','weight_sram_bytes','scale_sram_bytes',
            'activation_sram_bytes','output_sram_bytes','vector_ops','activation_delivery_bytes',
            'bank_peak_weight_bytes','bank_peak_activation_bytes')},
        row_mapping=dict(mode=mode,groups=fold,rows_per_group=group_rows,group_phase_skew_cycles=1,
            configuration_bytes=configuration_bytes,word_buffer_bytes=word_buffers,scale_register_bytes=scale_register_bytes,
            independent_fp8_weight_lanes=p.arrays*fold*p.columns,
            added_weight_lanes=p.arrays*(fold-1)*p.columns,
            costs='Extra row steering/injection and scale routing are candidate hardware capabilities. Storage and shared ports are charged; added wires/muxes have explicit counts but uncalibrated area/energy.'),
        dataflow='Independent OS row groups; group-major N / increasing-K partitions; finite word/bank/fanout grants. '
            'FP32 partition association changes and requires a separate numerical qualification.')
    if plan['scratch_bytes']>8*1024**2:raise ValueError('Folded context exceeds non-cache SRAM before other tasks')
    return tuple(code),plan


@lru_cache(maxsize=96)
def select_program(M,N,K,dtype,p,policy):
    if policy=='reference_os':return program(M,N,K,dtype,p)
    baseline=best_os(M,N,K,dtype,p)
    if policy=='best_os':return baseline
    if policy!='row_auto':raise ValueError('Explicit row mapping policy required')
    if dtype!='FP8_E4M3FN' or (N,K) not in ((128,4096),(4096,128)):return baseline
    choices=[baseline]
    for fold in (2,4):
        if M<=p.rows//fold:choices.append(folded_program(M,N,K,dtype,p,fold))
    return min(choices,key=lambda item:(item[1]['cycles'],item[1]['scratch_bytes']))


def reprogram_graph(graph,kernels,p,policy):
    tasks=[]
    for task in graph.tasks:
        k=kernels.get(task.id)
        if k is None:tasks.append(task);continue
        old=program(k.M,k.N,k.K,k.weight_dtype,p)[1]
        new=select_program(k.M,k.N,k.K,k.weight_dtype,p,policy)[1]
        if task.compute_cycles!=old['cycles'] or task.scratch_bytes<old['scratch_bytes']:
            raise ValueError('Only default-lowered tasks may be reprogrammed once')
        tasks.append(replace(task,compute_cycles=new['cycles'],scratch_bytes=task.scratch_bytes-old['scratch_bytes']+new['scratch_bytes']))
    return replace(graph,tasks=tuple(tasks))


class RowMappingKernelModel(NPUKernelModel):
    def __init__(self,profile,kernels,*,policy,evidence='epochs',auxiliary=None):
        self.policy=policy
        super().__init__(profile,kernels,evidence=evidence,auxiliary=auxiliary)

    def program_for(self,key):
        k=self.kernels[key]
        return select_program(k.M,k.N,k.K,k.weight_dtype,self.profile,self.policy)

    def record(self):
        record=super().record()
        record.update(execution_policy='row_mapping_v1',mapping_policy=self.policy,
            calibration='OS subgroup core needs pinned SCALE-Sim comparison; row steering/banking remain declared assumptions, not silicon calibration.')
        return record
