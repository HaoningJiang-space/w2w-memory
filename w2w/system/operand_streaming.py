"""Coordinate-qualified descriptor streaming of the same finite OS program.

Complete inputs and original scales are required. Each weight word must belong
to committed descriptors before its array tick. Mask ROM, validity state and
probe reads/ops are paid. The array owner, full cache object and coupled fetch
lifetimes remain conservative; this design makes no free early-release claim.
"""
from collections import Counter
from dataclasses import asdict,replace
from functools import lru_cache
from math import ceil

from w2w.common.fingerprints import digest_read_v1 as digest
from .npu_kernel import NPUInstruction,NPUKernelModel,program
from .row_mapping import best_os


def required_descriptors(M,N,K,plan,instruction,fragment_bytes=4096):
    if instruction.phase not in ('array','array_input_stall'):return 0
    needed=0;tick=instruction.array_tick
    for tile in plan['waves'][instruction.wave]:
        for c in range(tile['N']):
            k=tick-c
            if 0<=k<tile['K']:
                byte=(tile['n']+c)*K+tile['k']+k
                word=byte//32*32
                first,last=word//fragment_bytes,(word+31)//fragment_bytes
                for fragment in range(first,last+1):needed|=1<<fragment
    return needed


@lru_cache(maxsize=96)
def streaming_program(M,N,K,dtype,p):
    base,old=best_os(M,N,K,dtype,p)
    if dtype!='FP8_E4M3FN' or (N,K) not in ((128,4096),(4096,128)):return base,old,tuple(0 for _ in base)
    fragments=ceil(N*K/4096);mask_bytes=ceil(fragments/8)
    probe_bytes=3*ceil(mask_bytes/p.word_bytes)*p.word_bytes
    code=[];required=[];original=[];checked=0
    for index,instruction in enumerate(base):
        need=required_descriptors(M,N,K,old,instruction)
        if need&~checked:
            code.append(NPUInstruction('operand_probe',instruction.wave,instruction.array_tick,
                activation_sram_bytes=probe_bytes,vector_ops=ceil(fragments/64),
                bank_peak_activation_bytes=min(p.bank_port_bytes_per_cycle,probe_bytes)))
            required.append(need);original.append(None);checked|=need
        code.append(instruction);required.append(need);original.append(index)
    if checked!=(1<<fragments)-1:raise ValueError('Streaming schedule does not inspect all original weight coordinates')
    rom_bytes=len(set(required))*mask_bytes+2*len(code)
    extra_state=rom_bytes+2*mask_bytes+32
    fields=tuple(old['service']);plan=dict(old)
    plan.update(cycles=len(code),scratch_bytes=old['scratch_bytes']+extra_state,
        mac_utilization=M*N*K/(p.macs_per_cycle*len(code)),
        service={f:sum(getattr(i,f) for i in code) for f in fields},program_sha256=digest([asdict(i) for i in code]),
        peak_service={f:max(getattr(i,f) for i in code) for f in old['peak_service']},
        streaming=dict(fragment_bytes=4096,fragments=fragments,mask_rom_bytes=rom_bytes,extra_state_bytes=extra_state,
            probe_count=sum(i.phase=='operand_probe' for i in code),probe_read_bytes=probe_bytes,
            original_program_cycles=len(base),original_indices=original,required_masks=[hex(v) for v in required],
            base_plan=old,readiness='Actual row-major N/K word coordinates and original scale identity. Complete BF16 input before acquisition. Validity comes only from committed descriptors or paid cache lookup.',
            ownership='One nonpreemptive array group may wait for later descriptors. Existing full-matrix cache pin and miss fetch context survive until their original release conditions.'),
        dataflow='Same qualified OS mapping and FP32 association, with paid coordinate-mask probes and externally stalled instruction progress. No static epoch may bypass these stalls.')
    return tuple(code),plan,tuple(required)


def reprogram_streaming_graph(graph,kernels,p):
    tasks=[]
    for task in graph.tasks:
        k=kernels.get(task.id)
        if k is None:tasks.append(task);continue
        old=program(k.M,k.N,k.K,k.weight_dtype,p)[1]
        new=streaming_program(k.M,k.N,k.K,k.weight_dtype,p)[1]
        if task.compute_cycles!=old['cycles'] or task.scratch_bytes<old['scratch_bytes']:
            raise ValueError('Streaming graph must be reprogrammed once from default lowering')
        tasks.append(replace(task,compute_cycles=new['cycles'],scratch_bytes=task.scratch_bytes-old['scratch_bytes']+new['scratch_bytes']))
    return replace(graph,tasks=tuple(tasks))


class StreamingKernelModel(NPUKernelModel):
    def __init__(self,profile,kernels,*,auxiliary=None):
        self.execution=None;self.wait_cycles=Counter();self.waiting={}
        super().__init__(profile,kernels,evidence='cycles',auxiliary=auxiliary)

    def program_for(self,key):
        k=self.kernels[key]
        return streaming_program(k.M,k.N,k.K,k.weight_dtype,self.profile)[:2]

    def for_window(self,kernels,auxiliary):return StreamingKernelModel(self.profile,kernels,auxiliary=auxiliary)

    def bind_execution(self,execution):
        if execution.operand_readiness!='contiguous_prefix' or execution.spec.memory_request_bytes!=4096:
            raise ValueError('Streaming needs the paid canonical committed-descriptor bitmap')
        self.execution=execution

    def ready(self,key,state,task):
        if key not in self.kernels or 'streaming' not in self.plans[key]:return super().ready(key,state,task)
        if task.stream is None:raise ValueError('Streaming matrix has no explicit original scales/data contract')
        first=next(int(v,16) for v in self.plans[key]['streaming']['required_masks'] if int(v,16))
        frontier=self.execution.operand_frontiers[key]
        return state.get('stream_scale_delivered',0)==task.stream.scale_bytes and first&~frontier.mask==0

    def service(self,execution,key):
        if 'streaming' not in self.plans[key]:return super().service(execution,key)
        k=self.kernels[key];code,plan,requirements=streaming_program(k.M,k.N,k.K,k.weight_dtype,self.profile)
        cursor=self.cursors[key]
        if cursor==len(code):return
        need=requirements[cursor];available=execution.operand_frontiers[key].mask
        if need&~available:
            self.wait_cycles[key]+=1
            if key not in self.waiting:
                self.waiting[key]=execution.now
                execution.log('npu_operand_wait_start',task=key,tile=execution.tasks[key].tile,program_cycle=cursor,
                    required_mask=hex(need),committed_mask=hex(available))
            return
        if key in self.waiting:
            begin=self.waiting.pop(key)
            execution.log('npu_operand_wait_end',task=key,tile=execution.tasks[key].tile,program_cycle=cursor,
                begin_ps=begin,cycles=(execution.now-begin)//self.profile.period_ps)
        self.cursors[key]+=1;row=code[cursor]
        execution.busy_ps[execution.tasks[key].tile]+=self.profile.period_ps
        execution.log('npu_cycle',task=key,tile=execution.tasks[key].tile,program_cycle=cursor,**asdict(row))
        if self.cursors[key]==len(code):
            task=execution.tasks[key];state=execution.state[key]
            if state['read_bytes']!=sum(r.size_bytes for r in task.reads):raise ValueError('Streaming output completed before all original weights/scales')
            state.update(stream_consumed=task.stream.weight_data_bytes,stream_scale_consumed=True,
                finish_ps=execution.now+self.profile.period_ps)
            self.owners.pop(task.tile,None)

    def record(self):
        if self.waiting:raise ValueError('Array output recorded with unresolved operand waits')
        record=super().record()
        record.update(execution_policy='operand_streaming_v1',operand_wait_cycles=dict(self.wait_cycles),
            operand_policy='Complete input/scales plus coordinate-qualified committed descriptors; paid mask probes; complete dot products before logical output.',
            interval_contract='Dynamic cycle evidence includes paid probes and explicit operand stalls under retained nonpreemptive ownership. Native/NoC/fetch/cache behavior is unchanged.')
        return record
