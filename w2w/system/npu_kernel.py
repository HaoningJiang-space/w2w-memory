"""Finite OS array programs, selected by GEMM shape, on the one system kernel.

Input SRAM reads may feed a paid, bounded fanout. Weights are row-major in
DRAM and output-interleaved across modeled SRAM banks. Local word buffers,
FP32 accumulators and K-partial storage occupy the original cluster SRAM.
"""
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from functools import lru_cache
from math import ceil
from w2w.common.fingerprints import digest_read_v1 as digest


@dataclass(frozen=True)
class ArrayTile:
    m: int
    n: int
    k: int
    M: int
    N: int
    K: int


@dataclass(frozen=True)
class NPUInstruction:
    phase: str
    wave: int
    array_tick: int
    macs: int = 0
    weight_sram_bytes: int = 0
    activation_sram_bytes: int = 0
    output_sram_bytes: int = 0
    vector_ops: int = 0
    accumulator_register_bytes: int = 0
    activation_delivery_bytes: int = 0
    bank_stall: bool = False
    scale_sram_bytes: int = 0
    bank_peak_weight_bytes: int = 0
    bank_peak_activation_bytes: int = 0


def array_tiles(M,N,K,p,weight_dtype='FP8_E4M3FN'):
    spatial=ceil(M/p.rows)*ceil(N/p.columns)
    # No sub-128 hidden groups: original FP8 scale references survive K sharding.
    if weight_dtype=='FP8_E4M3FN':
        candidates=[s for s in range(1,min(max(1,p.arrays//spatial),max(1,K//128))+1) if K%s==0 and K//s%128==0]
        split=max(candidates,default=1);cuts=[i*K//split for i in range(split+1)]
    else:
        # BF16 has no FP8 scale boundary. Unequal, word-aligned K pieces
        # retain a final short word, with explicit SRAM padding in the IR.
        words=ceil(K*2/p.word_bytes);split=min(max(1,p.arrays//spatial),words)
        cuts=[min(K,(i*words//split)*(p.word_bytes//2)) for i in range(split)]+[K]
    tiles=tuple(ArrayTile(m,n,a,min(p.rows,M-m),min(p.columns,N-n),b-a)
        for m in range(0,M,p.rows) for n in range(0,N,p.columns) for a,b in zip(cuts,cuts[1:]))
    return tuple(tiles[i:i+p.arrays] for i in range(0,len(tiles),p.arrays)),split


def _core_macs(tile,t):
    return sum(max(0,min(tile.N,t-r+1)-max(0,t-r-tile.K+1)) for r in range(tile.M))


@lru_cache(maxsize=256)
def program(M,N,K,weight_dtype,p):
    waves,split=array_tiles(M,N,K,p,weight_dtype);instructions=[];bpp=1 if weight_dtype=='FP8_E4M3FN' else 2
    if bpp==1:
        scales=4*ceil(N/128)*ceil(K/128)
        if scales>p.weight_read_bytes_per_cycle:raise ValueError('Explicit scale-load tiling required')
        instructions.append(NPUInstruction('scale_load',-1,0,scale_sram_bytes=scales))
    for wave_id,tiles in enumerate(waves):
        cache={};duration=max(t.K for t in tiles)+p.rows+p.columns-2
        for tick in range(duration):
            loads=[];broadcast=defaultdict(list);macs=0;dequant=0;delivery=0
            for array,tile in enumerate(tiles):
                macs+=_core_macs(tile,tick)
                for c in range(tile.N):
                    k=tick-c
                    if not 0<=k<tile.K:continue
                    dequant+=int(bpp==1)
                    word=(tile.k+k)*bpp//p.word_bytes;identity=('w',array,c)
                    if cache.get(identity)!=word:
                        loads.append(('w',(tile.n+c)%p.banks,identity,word))
                for r in range(tile.M):
                    k=tick-r
                    if not 0<=k<tile.K:continue
                    delivery+=2
                    word=(tile.k+k)*2//p.word_bytes;identity=('x',array,r)
                    if cache.get(identity)!=word:
                        broadcast[(tile.m+r,word)].append((identity,word))
            for (m,word),receivers in broadcast.items():
                for offset in range(0,len(receivers),p.input_broadcast_fanout):
                    loads.append(('x',(m+word)%p.banks,tuple(receivers[offset:offset+p.input_broadcast_fanout]),word))
            # Each cycle has finite per-bank and aggregate ports. A stalled
            # input freezes the array wave; no future MAC or output is released.
            while True:
                live=Counter();used=Counter();pending=[]
                for kind,bank,identity,word in loads:
                    limit=p.weight_read_bytes_per_cycle if kind=='w' else p.activation_read_bytes_per_cycle
                    if (live[kind,bank]+p.word_bytes>p.bank_port_bytes_per_cycle or used[kind]+p.word_bytes>limit):
                        pending.append((kind,bank,identity,word));continue
                    live[kind,bank]+=p.word_bytes;used[kind]+=p.word_bytes
                    if kind=='w':cache[identity]=word
                    else:
                        for receiver,value in identity:cache[receiver]=value
                if loads and not used:raise ValueError('A SRAM word cannot be serviced by this finite port')
                if pending:
                    instructions.append(NPUInstruction('array_input_stall',wave_id,tick,
                        weight_sram_bytes=used['w'],activation_sram_bytes=used['x'],bank_stall=True,
                        bank_peak_weight_bytes=max((v for (kind,_),v in live.items() if kind=='w'),default=0),
                        bank_peak_activation_bytes=max((v for (kind,_),v in live.items() if kind=='x'),default=0)))
                    loads=pending;continue
                if dequant>p.vector_ops_per_cycle or delivery>p.activation_read_bytes_per_cycle:
                    raise ValueError('Array input conversion/fanout exceeds reference ports')
                instructions.append(NPUInstruction('array',wave_id,tick,macs,used['w'],used['x'],0,dequant,
                    macs*8,delivery,
                    bank_peak_weight_bytes=max((v for (kind,_),v in live.items() if kind=='w'),default=0),
                    bank_peak_activation_bytes=max((v for (kind,_),v in live.items() if kind=='x'),default=0)))
                break
        size=sum(t.M*t.N*4 for t in tiles)
        while size:
            n=min(size,p.output_write_bytes_per_cycle,p.banks*p.bank_port_bytes_per_cycle)
            instructions.append(NPUInstruction('partial_store',wave_id,duration,output_sram_bytes=n));size-=n
    if split>1:
        # Reuse the now-free array accumulator registers: spare-array K
        # partitioning guarantees M*N <= the available physical MAC cells.
        # Every element observes increasing K order. A whole output is never
        # stored before its final dependent addition, even if all work counts
        # would fit a single aggregate bandwidth/ops grant.
        if M*N>p.macs_per_cycle:raise ValueError('K-reduction registers exceed paid array accumulators')
        for part in range(split):
            remaining=M*N;tick=0
            while remaining:
                count=min(remaining,p.activation_read_bytes_per_cycle//4,p.banks*p.bank_port_bytes_per_cycle//4,
                    p.vector_ops_per_cycle if part else remaining)
                instructions.append(NPUInstruction('ordered_k_load' if not part else 'ordered_k_add',len(waves),tick,
                    activation_sram_bytes=4*count,vector_ops=count if part else 0,
                    accumulator_register_bytes=(8 if part else 4)*count))
                remaining-=count;tick+=1
        size=M*N*4;tick=0
        while size:
            count=min(size,p.output_write_bytes_per_cycle,p.banks*p.bank_port_bytes_per_cycle)
            instructions.append(NPUInstruction('ordered_k_final_store',len(waves),tick,
                output_sram_bytes=count,accumulator_register_bytes=count))
            size-=count;tick+=1
    if sum(i.macs for i in instructions)!=M*N*K:raise ValueError('Array mapping changed mathematical MAC work')
    metadata=dict(M=M,N=N,K=K,weight_dtype=weight_dtype,k_partitions=split,
        waves=[[asdict(t) for t in wave] for wave in waves],cycles=len(instructions),
        array_cycles=sum(i.phase=='array' for i in instructions),bank_stall_cycles=sum(i.bank_stall for i in instructions),
        macs=M*N*K,scratch_bytes=p.context_buffer_bytes+M*N*split*4,
        mac_utilization=M*N*K/(p.macs_per_cycle*len(instructions)),
        service={field:sum(getattr(i,field) for i in instructions) for field in
            ('weight_sram_bytes','scale_sram_bytes','activation_sram_bytes','output_sram_bytes','vector_ops',
             'accumulator_register_bytes','activation_delivery_bytes')},
        dataflow='Output-stationary M/N tiling with bounded arrays; spare arrays may partition K. '
            'All K partials reduce in increasing K order before logical output. '
            'One nonpreemptive array group per cluster, bounded input broadcast and per-array 32 B word buffers. '
            'Bank layouts are declared assumptions, not calibrated SRAM macros.')
    metadata['program_sha256']=digest([asdict(i) for i in instructions])
    metadata['peak_service']={field:max(getattr(i,field) for i in instructions) for field in
        ('macs','weight_sram_bytes','scale_sram_bytes','activation_sram_bytes','output_sram_bytes',
         'vector_ops','activation_delivery_bytes','bank_peak_weight_bytes','bank_peak_activation_bytes')}
    return tuple(instructions),metadata


class NPUKernelModel:
    def __init__(self,profile,kernels,*,evidence='epochs',auxiliary=None):
        if evidence not in ('epochs','cycles'):raise ValueError('Explicit array evidence required')
        self.evidence=evidence
        self.profile=profile;self.kernels=dict(kernels);self.cursors=Counter();self.owners={}
        self.auxiliary=dict(auxiliary or {});self.aux_cursors=Counter()
        from .npu_auxiliary import auxiliary_program
        self.aux_programs={k:auxiliary_program(v,profile) for k,v in self.auxiliary.items()}
        self.plans={k:program(v.M,v.N,v.K,v.weight_dtype,profile)[1] for k,v in self.kernels.items()}

    def validate(self,spec,graph):
        for c in spec.stack.compute_clusters:self.profile.validate_cluster(c)
        tasks={t.id:t for t in graph.tasks}
        objects={o.id:o for o in graph.objects};incoming=Counter()
        for edge in graph.data:incoming[edge.consumer]+=edge.size_bytes
        for key,k in self.kernels.items():
            if key not in tasks:raise ValueError('NPU kernel has no physical task')
            task=tasks[key];plan=self.plans[key]
            if task.compute_cycles!=plan['cycles']:raise ValueError('GEMM task did not use the current complete array program')
            expected=k.activation_storage_bytes+(k.weight_storage_bytes if k.weight_object not in objects else 0)
            if incoming[key]!=expected:raise ValueError('GEMM lacks its actual input/virtual-weight shape and word padding')
            if task.scratch_bytes<plan['scratch_bytes']:raise ValueError('NPU buffers/partials are not charged to task SRAM')
            if task.stream and (task.stream.macs!=k.macs or task.stream.weight_data_bytes!=k.weight_bytes):
                raise ValueError('GEMM shape differs from weight/work identity')
        for key,work in self.auxiliary.items():
            cycles=len(self.aux_programs[key])
            if key not in tasks or tasks[key].compute_cycles!=cycles:raise ValueError('Vector/transpose/append service cycles unpaid')
            from .npu_auxiliary import output_buffer_bytes
            owned=sum(e.size_bytes for e in graph.data if e.producer==key)+tasks[key].scratch_bytes
            if owned<output_buffer_bytes(work):raise ValueError('Vector output storage must be owned before production')

    def auxiliary_service(self,key):
        tick=self.aux_cursors[key];self.aux_cursors[key]+=1
        return self.aux_programs[key][tick]

    def ready(self,key,state,task):
        if key not in self.kernels:return True
        return state['read_bytes']==sum(r.size_bytes for r in task.reads)

    def owner(self,tile,keys,state,now):
        old=self.owners.get(tile)
        if old is not None and (state[old]['finish_ps'] is None or state[old]['finish_ps']>now):return old
        self.owners.pop(tile,None)
        # Scalar work still uses the same shared cluster grant. Once an array
        # kernel acquires the group, its register state is not swapped for free.
        for key in keys:
            if state[key]['finish_ps'] is None and key in self.kernels:
                self.owners[tile]=key;return key
        return None

    def service(self,execution,key):
        task=execution.tasks[key];k=self.kernels[key];p=self.profile
        instructions,_=program(k.M,k.N,k.K,k.weight_dtype,p)
        cursor=self.cursors[key]
        if cursor==len(instructions):return
        if self.evidence=='epochs':
            plan=self.plans[key];self.cursors[key]=len(instructions)
            execution.busy_ps[task.tile]+=p.period_ps*len(instructions)
            state=execution.state[key];state['finish_ps']=execution.now+p.period_ps*len(instructions)
            if task.stream:state.update(stream_consumed=task.stream.weight_data_bytes,stream_scale_consumed=True)
            execution.log('npu_epoch',task=key,tile=task.tile,end_ps=state['finish_ps'],cycles=len(instructions),
                program_sha256=plan['program_sha256'],macs=k.macs,service=plan['service'],peak_service=plan['peak_service'])
            return
        row=instructions[cursor];self.cursors[key]+=1
        execution.busy_ps[task.tile]+=p.period_ps
        execution.log('npu_cycle',task=key,tile=task.tile,program_cycle=cursor,**asdict(row))
        if self.cursors[key]==len(instructions):
            state=execution.state[key]
            if task.stream:state.update(stream_consumed=task.stream.weight_data_bytes,stream_scale_consumed=True)
            state['finish_ps']=execution.now+p.period_ps
            self.owners.pop(task.tile,None)

    def record(self):
        return dict(schema='w2w.shape-aware-npu.v1',profile=asdict(self.profile),
            kernels={k:asdict(v) for k,v in self.kernels.items()},plans=self.plans,
            auxiliary=self.auxiliary,
            operand_policy='Complete scale/weight/input committed before array acquisition; no illegal partial SiLU.',
            scheduling='Two original compute contexts, one nonpreemptive shared array group per cluster. '
                'Original Native/RX/fetch/cache behavior retained. All local buffers/partials paid in task scratch.',
            evidence=self.evidence,
            interval_contract='All inputs committed, nonpreemptive array ownership, internal PE ports separate from original fabric DMA ports. '
                'Fixed internal program has no external output before end; epochs retain its hash/work/port peaks. '
                'Native/NoC/request/cache clocks are not skipped.',
            calibration='SCALE-Sim OS array-core comparison plus independent work/port audit; no silicon calibration')
