"""One coarse spatial COST REFERENCE; it is not an implemented transport profile.

32 port locations on a uniform 8x4 grid, domain-local vertical HB landing, logic
CDC at that landing, then Manhattan data collection to the center. Grid cells
are not calibrated array footprints; logic wire timing uses the existing recipe.
"""
from math import ceil


def grid_collection_reference():
    domains=[]
    for y in range(4):
        for x in range(8):
            a=((2*x-7)*3250//2,(2*y-3)*8250//2)
            length=abs(a[0])+abs(a[1]);cycles=ceil(length/2000)
            domains.append(dict(domain=y*8+x,array_port_um=a,hb_logic_landing_um=a,
                aggregation_um=(0,0),logic_collection_manhattan_um=length,
                data_bits=128,pipeline_cycles_reference=cycles,
                data_wire_bit_mm=128*length/1000,data_pipeline_bits_reference=128*cycles))
    return dict(scope='coarse 26x33mm, 8x4 domain-port cost reference; NOT charged in current execution',
        spatially_calibrated=False,included_in_runtime=False,domains=domains,
        data_wire_bit_mm_per_memory=sum(d['data_wire_bit_mm'] for d in domains),
        data_pipeline_bits_per_memory_reference=sum(d['data_pipeline_bits_reference'] for d in domains),
        total_domain_to_center_manhattan_mm=sum(d['logic_collection_manhattan_um'] for d in domains)/1000,
        notes='data only; no assumed controller/array area, clock tree, command/address, CDC metadata or return-control cost')
