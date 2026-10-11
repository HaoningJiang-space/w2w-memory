"""Finite ordered vector/SRAM phases, including reduction and conversion barriers."""
from math import ceil

FIELDS=('activation_sram_bytes','output_sram_bytes','weight_sram_bytes','vector_ops','activation_delivery_bytes')


def phase(name,*,read=0,write=0,weights=0,ops=0,delivery=0,floor=1):
    return dict(name=name,activation_sram_bytes=read,output_sram_bytes=write,weight_sram_bytes=weights,
        vector_ops=ops,activation_delivery_bytes=delivery,cycles_floor=floor)


def limits(profile):
    return dict(activation_sram_bytes=profile.activation_read_bytes_per_cycle,output_sram_bytes=profile.output_write_bytes_per_cycle,
        weight_sram_bytes=profile.weight_read_bytes_per_cycle,vector_ops=profile.vector_ops_per_cycle,
        activation_delivery_bytes=profile.activation_read_bytes_per_cycle)


def work(phases):
    phases=tuple(phases)
    return dict(**{f:sum(p[f] for p in phases) for f in FIELDS},phases=phases)


def auxiliary_program(spec,profile):
    if set(spec)-set(FIELDS)-{'phases'}:raise ValueError('Unrecognized auxiliary resource work')
    total={f:spec.get(f,0) for f in FIELDS};phases=spec.get('phases') or (dict(total,cycles_floor=1),)
    if any(type(v) is not int or v<0 for v in total.values()):raise ValueError('Finite vector work required')
    if any(sum(p.get(f,0) for p in phases)!=total[f] for f in FIELDS):raise ValueError('Vector phase totals differ')
    rows=[];ports=limits(profile)
    for p in phases:
        if set(p)-set(FIELDS)-{'name','cycles_floor'}:raise ValueError('Unrecognized phase resource work')
        floor=p.get('cycles_floor',1)
        if type(floor) is not int or floor<1:raise ValueError('Explicit positive reduction latency required')
        if any(type(p.get(f,0)) is not int or p.get(f,0)<0 for f in FIELDS):raise ValueError('Finite phase service required')
        cycles=max(floor,max(ceil(p.get(f,0)/ports[f]) for f in FIELDS))
        for tick in range(cycles):rows.append({f:min(max(0,p.get(f,0)-tick*ports[f]),ports[f]) for f in FIELDS})
    return tuple(rows)
