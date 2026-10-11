"""Explicit whole-model residency; never alias 94 layer catalogs onto 8 GiB."""
from collections import Counter
from dataclasses import asdict,dataclass
from math import ceil
from .resources import inventory
from w2w.domain.execution import ResidentObject
from w2w.mapping.moe_batch_lowering import full_catalog
from w2w.common.fingerprints import digest_read_v1 as digest


@dataclass(frozen=True)
class LLMProfile:
    hidden:int=4096
    intermediate:int=1536
    experts:int=128
    topk:int=8
    layers:int=94
    query_heads:int=64
    kv_heads:int=4
    head_dim:int=128
    vocabulary:int=151936
    kv_tokens_per_request:int=256
    inter_stage_bytes_per_ns:int=128
    inter_stage_latency_ps:int=100000
    inter_stage_packet_bytes:int=4096

    @classmethod
    def from_config(cls,c):
        if c.get('tie_word_embeddings') is not False or c.get('sliding_window') is not None:
            raise ValueError('Explicit untied full-attention Qwen3 deployment required')
        p=cls(**{field:c[key] for field,key in dict(hidden='hidden_size',intermediate='moe_intermediate_size',
            experts='num_experts',topk='num_experts_per_tok',layers='num_hidden_layers',query_heads='num_attention_heads',
            kv_heads='num_key_value_heads',head_dim='head_dim',vocabulary='vocab_size').items()})
        if p.query_heads%p.kv_heads or p.hidden%128 or p.intermediate%128:raise ValueError('GQA/quantization contract differs')
        return p


def context_catalog(machine,shape,layers,baseline,profile,*,embedding=False,head=False,context_projection_policy='whole_matrix_local'):
    if context_projection_policy not in ('whole_matrix_local','output_sharded'):raise ValueError('Explicit legal context projection mapping required')
    catalog=full_catalog(machine,shape,layers,baseline);objects=list(catalog['objects']);used=Counter()
    for o in objects:used[o.memory]=max(used[o.memory],o.offset_bytes+o.size_bytes)
    memories={m.id:m for m in machine.memories};tiles={t.router_id:t.id for t in machine.tiles};placements={}
    def allocate(key,size,preferred):
        size=ceil(size/32)*32
        order=sorted(memories,key=lambda m:(memories[m].home_tile!=machine.endpoint_router(preferred),used[m],m))
        memory=next((m for m in order if used[m]+size<=memories[m].capacity_bytes),None)
        if memory is None:raise ValueError('Full independent context/embedding/head catalog exceeds physical per-domain capacity')
        objects.append(ResidentObject(key,memory,used[memory],size,storage_id=key));used[memory]+=size
        placements[key]=tiles[memories[memory].home_tile]
    projection_shards={}
    for local_layer,layer in enumerate(layers):
        root=f'L{layer}/context/'
        for phase,N,K in (('q',profile.query_heads*profile.head_dim,profile.hidden),
                ('k',profile.kv_heads*profile.head_dim,profile.hidden),('v',profile.kv_heads*profile.head_dim,profile.hidden),
                ('o',profile.hidden,profile.query_heads*profile.head_dim)):
            if context_projection_policy=='whole_matrix_local':
                allocate(root+phase,N*K+4*ceil(N/128)*ceil(K/128),'c0')
            else:
                from w2w.mapping.context_projections import output_rows
                rows=output_rows(phase,N,K,machine,local_layer,profile.kv_heads)
                for row in rows:
                    key=root+phase+f'/rows{row["row_begin"]:05d}'
                    allocate(key,row['N']*K+4*(row['N']//128)*ceil(K/128),row['preferred_cluster'])
                    row['weight_object']=key
                projection_shards[root+phase]=rows
        for kind,n in (('input_norm',profile.hidden),('post_norm',profile.hidden),('q_norm',profile.head_dim),('k_norm',profile.head_dim)):
            allocate(root+kind,2*n,'c0')
        allocate(root+'rope_table',profile.kv_tokens_per_request*profile.head_dim*4,'c0')
    for kind,include in (('embedding',embedding),('lm_head',head)):
        if not include:continue
        for start in range(0,profile.vocabulary,4096):
            N=min(4096,profile.vocabulary-start)
            # Both are BF16 and untied, matching the pinned exclusion list.
            allocate(f'{kind}/{start}',2*N*profile.hidden,f'c{(start//4096)%len(machine.tiles)}')
    if head:allocate('final_norm',2*profile.hidden,'c0')
    catalog.update(objects=tuple(objects),context_placements=placements,llm_profile=asdict(profile),embedding=embedding,head=head)
    if projection_shards:catalog.update(context_projection_policy=context_projection_policy,context_projection_shards=projection_shards)
    return catalog


def deployment(machine,shape,profile,baseline='up_local',context_projection_policy='whole_matrix_local'):
    stages=[]
    for index,start in enumerate(range(0,profile.layers,2)):
        layers=tuple(str(i) for i in range(start,min(start+2,profile.layers)))
        catalog=context_catalog(machine,shape,layers,baseline,profile,embedding=index==0,head=start+2>=profile.layers,
            context_projection_policy=context_projection_policy)
        stages.append(dict(stage=index,layers=layers,resident_bytes=sum(o.size_bytes for o in catalog['objects']),
            catalog_sha256=digest([asdict(o) for o in catalog['objects']]),objects=len(catalog['objects']),
            embedding=catalog['embedding'],lm_head=catalog['head']))
    resources=inventory(machine.stack)
    return dict(schema='w2w.full-llm-deployment.v1',stages=stages,stack_copies=len(stages),profile=asdict(profile),
        machine_sha256=digest(asdict(machine)),resources_per_stack=resources,
        dram_capacity_bytes=len(stages)*sum(m.capacity_bytes for m in machine.memories),
        resident_model_bytes=sum(s['resident_bytes'] for s in stages),
        inter_stage=dict(links=len(stages)-1,feedback_links=1,bytes_per_ns=profile.inter_stage_bytes_per_ns,
            latency_ps=profile.inter_stage_latency_ps,packet_bytes=profile.inter_stage_packet_bytes,
            direction='Point-to-point activation pipeline plus final token-feedback link; explicit finite source/destination ports.',
            buffers_per_endpoint_bytes=2*32*profile.hidden*2,control_state_bytes_per_endpoint=2*64*16,
            control_bytes_per_packet=16,cell_bytes=128,sideband_bits=64,
            port_sharing='Existing 128 B/cycle SRAM fabric ports; transfer only after both previous local windows drain. Next local window waits for RX commit and own TX release; real c15 ingress/export NoC edges.',
            area_um2=None,energy_pj_per_byte=None,calibrated=False),
        kv=dict(location='Reserved portion of existing non-weight-cache SRAM',tokens_per_request=profile.kv_tokens_per_request,
            bytes_per_token_layer=2*profile.kv_heads*profile.head_dim*2,policy='BF16 append-only K/V, no DRAM writes inferred from the read-only Native backend; capacity rejection rather than cache shrink.'),
        input_assumptions=dict(arrivals='Modeled simultaneous admission, not captured',
            prompt_length='Captured prefill row count used as an explicit context-length assumption; text/token IDs unavailable',
            embedding_addresses='Unknown until a separately declared timing-address policy is supplied; no full-model execution accepted without one',
            activations='Timing shapes only, no real numerical inference claim'),
        scope='Legal capacity and explicit replicated V3 pipeline specification. No TTFT/TPOT or performance claim without complete physical stage/serving evidence.')
