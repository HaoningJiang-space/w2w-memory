"""Declared small one-domain machine; identical hardware in each mode pair."""
from dataclasses import replace
from w2w.architecture.presets import vertical_memory
from w2w.architecture.compiler import compile_machine
from w2w.domain.execution import ResidentObject,ReadAccess,StreamGemm,ComputeTask,ExecutionGraph


def inputs(case,length=8192):
    if case not in ('continuous','pressure','inserted'):raise ValueError('Unknown island input')
    stack=vertical_memory('distributed',rows=1,columns=1)
    domain=stack.dram_domains[0];gateway=stack.gateways[0];group=stack.bank_groups[0]
    if case=='pressure':
        domain=replace(domain,return_atoms=2)
        gateway=replace(gateway,router_access_cycles=64)
    group=replace(group,domain_ids=(domain.id,))
    port=replace(stack.vertical_ports[0],domain_ids=(domain.id,),data_bits=128,hb_sites=192)
    path=next(p for p in stack.collection_paths if p.domain_id==domain.id)
    stack=replace(stack,name='island-'+case,dram_domains=(domain,),gateways=(gateway,),bank_groups=(group,),
        vertical_ports=(port,),collection_paths=(path,),resource_budget=None)
    spec=compile_machine(stack);profile=stack.compute_clusters[0].profile
    obj=ResidentObject('W',group.id,0,length+32)
    base=ComputeTask('gemm','c3',0,(ReadAccess('W',length,32),ReadAccess('W',0,length)),
        stream=StreamGemm('W',length,32,length*256,profile.macs_per_cycle,profile.weight_read_bytes_per_cycle))
    tasks=(base,)
    if case=='inserted':tasks+=(replace(base,id='late',tile='c2',release_ps=200*3760),)
    return spec,ExecutionGraph(tasks,(obj,))
