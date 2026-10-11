"""Output-row partition with unique original 128x128 scales and real packing."""
from dataclasses import dataclass, asdict
from collections import Counter


@dataclass(frozen=True)
class DomainWeightSlice:
    matrix_id: str
    phase: str
    domain_id: str
    tile_id: str
    output_rows: tuple[int,int]
    reduction_columns: int
    source_data_offset_bytes: int
    domain_offset_bytes: int
    data_bytes: int
    original_scale_indices: tuple[int,...]
    owned_scale_indices: tuple[int,...]
    scale_owners: tuple[str,...]
    scale_valid_bytes: int
    scale_storage_bytes: int


def domain_weight_catalog(logical, stack, weights, specification):
    h,_,width,_,_=logical.shape
    if h%128 or width%128:raise ValueError('Original quantization groups must remain 128x128')
    groups={g.id:g for g in stack.bank_groups};domains={d.id:d for d in stack.dram_domains}
    locations={w.tensor:w for w in weights};tile_by_domain={t.domain_id:t.id for t in specification.tiles}
    if set(locations)!={name for name,_ in logical.weight_sizes}:
        raise ValueError('Placement must cover the complete expert catalog, never only evaluated experts')
    offsets=Counter();slices=[];matrices={}
    for name,size in logical.weight_sizes:
        phase=name.rsplit('/',1)[-1];location=locations[name]
        if phase not in ('gate','up','down') or size!=location.size_bytes:
            raise ValueError('Explicit canonical FFN weights required')
        rows,cols=(h,width) if phase=='down' else (width,h)
        ds=groups[location.memory].domain_ids;n=len(ds)
        if n!=8 or rows%n or rows*cols+(rows//128)*(cols//128)*4!=size:
            raise ValueError('Partition or original scale accounting changed')
        per=rows//n;refs=[]
        for i in range(n):
            first,last=i*per,(i+1)*per
            refs.append(tuple(r*(cols//128)+c for r in range(first//128,(last-1)//128+1) for c in range(cols//128)))
        owners={s:next(i for i,ref in enumerate(refs) if s in ref) for ref in refs for s in ref}
        if set(owners)!=set(range((rows//128)*(cols//128))):raise ValueError('Missing original scale group')
        matrix=[]
        for i,d in enumerate(ds):
            if d not in tile_by_domain:raise ValueError('No physical domain tile')
            owned=tuple(s for s in refs[i] if owners[s]==i);valid=4*len(owned)
            storage=((valid+31)//32)*32
            data=per*cols;at=offsets[d]
            if data%32 or at%32:raise ValueError('Canonical domain reads must pay 32-byte alignment')
            offsets[d]+=data+storage
            if offsets[d]>domains[d].capacity_bytes:raise ValueError('Offline full catalog exceeds physical domain capacity')
            row=DomainWeightSlice(name,phase,d,tile_by_domain[d],(i*per,(i+1)*per),cols,
                location.offset_bytes+i*data,at,data,refs[i],owned,tuple(ds[owners[s]] for s in refs[i]),valid,storage)
            slices.append(row);matrix.append(asdict(row))
        matrices[name]=dict(rows=rows,columns=cols,original_group_shape=(128,128),logical_bytes=size,
            source_memory_view=location.memory,source_object_offset_bytes=location.offset_bytes,
            source_scale_base_bytes=location.offset_bytes+rows*cols,
            slices=matrix,offline_layout='output rows contiguous inside each real domain; no runtime transpose/gather',
            scale_contract='unique original scale bytes at their owner; other slices receive explicit scale multicast')
    return dict(schema='w2w.domain-weight-catalog.v1',matrices=matrices,
        slices=tuple(slices),domain_storage_bytes=dict(offsets),
        logical_catalog_bytes=sum(size for _,size in logical.weight_sizes),
        physical_catalog_bytes=sum(offsets.values()),
        contract='Full-catalog offline repacking is a separately prepared initial memory image, not a measured free migration. '
                 'No new scale or hidden-reduction partial is created. 32-byte padding is stored/read and counted.')
