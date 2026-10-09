"""Restore a physical machine record without invoking any topology generator."""
from .compute_fabric import ReticleRegion,ComputeCluster,ComputeProfile,Router
from .memory_wafer import DRAMDomain,MemoryBankGroup,NativePolicy
from .physical_graph import FabricChannel,WireSegment
from .vertical_interface import VerticalPort,MemoryGateway,CollectionPath,ExternalPort
from .wafer_stack import WaferStack


def from_record(record):
    if record['schema']!='w2w.wafer-stack.v3':raise ValueError('Unknown physical machine schema')
    def restore(cls,rows):
        values=[]
        for row in rows:
            row=dict(row)
            for key in ('origin_um','size_um','position_um','domain_ids','start_um','end_um'):
                if key in row:row[key]=tuple(row[key])
            values.append(cls(**row))
        return tuple(values)
    clusters=[]
    for row in record['compute_clusters']:
        row=dict(row);row['profile']=ComputeProfile(**row['profile']);row['position_um']=tuple(row['position_um'])
        clusters.append(ComputeCluster(**row))
    channels=[]
    for row in record['lateral_links']:
        row=dict(row);row['segments']=restore(WireSegment,row['segments']);channels.append(FabricChannel(**row))
    return WaferStack(record['name'],restore(ReticleRegion,record['compute_reticles']),tuple(clusters),
        restore(Router,record['routers']),restore(ReticleRegion,record['memory_regions']),
        restore(DRAMDomain,record['dram_domains']),tuple(channels),
        restore(VerticalPort,record['vertical_ports']),restore(MemoryGateway,record['gateways']),
        restore(MemoryBankGroup,record['bank_groups']),restore(CollectionPath,record['collection_paths']),
        restore(ExternalPort,record['external_ports']),NativePolicy(**record['native_policy']),record['wafer_diameter_um'])
