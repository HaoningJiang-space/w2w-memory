"""Non-executable storage/readiness contracts for the delivery-necessity gate."""
from dataclasses import dataclass,asdict
from math import ceil


@dataclass(frozen=True)
class CollectiveResidencyDirectory:
    slices: int = 8
    data_bytes_per_neighborhood: int = 184*1024**2
    entries: int = 512
    original_tag_bits: int = 128
    lookup_slots: int = 32
    lookup_cycles: int = 1
    slice_data_bytes: int = 65536
    maximum_owned_scale_bytes: int = 128
    original_matrix_bytes: int = 524416

    def __post_init__(self):
        if any(type(v) is not int or v<1 for v in asdict(self).values()):
            raise ValueError('Positive integer directory/storage budgets required')
        if self.slices!=8 or self.original_tag_bits!=128 or self.data_bytes_per_neighborhood%self.slices:
            raise ValueError('This contract preserves eight equal data pools and original byte-sized tags')
        if (self.slice_data_bytes%32 or self.maximum_owned_scale_bytes!=128 or
                self.slice_data_bytes*self.slices+128!=self.original_matrix_bytes):
            raise ValueError('Fixed original FP8 matrix and aligned maximum scale ownership required')

    def record(self):
        stride=self.slice_data_bytes+self.maximum_owned_scale_bytes
        data_per_slice=self.data_bytes_per_neighborhood//self.slices
        slots=min(self.entries,data_per_slice//stride)
        original_slots=min(self.entries,self.data_bytes_per_neighborhood//self.original_matrix_bytes)
        if slots!=original_slots:raise ValueError('This collective reference would change resident matrix count')
        # Keep original whole-matrix tag/pin/LRU state; add paid per-slice
        # valid/filling flags. Slot addresses derive from one common slot index.
        tags=self.entries*(self.original_tag_bits//8+ceil(2*self.slices/8))
        return dict(**asdict(self),executable=False,collective_replacement=True,
            slot_stride_bytes=stride,slots=slots,original_slots=original_slots,
            tag_bytes=tags,original_tag_bytes=self.entries*self.original_tag_bits//8,
            metadata_bytes=tags+self.lookup_slots*12+16,
            allocated_data_bytes=slots*self.slices*stride,
            slot_padding_bytes_per_matrix=self.slices*stride-self.original_matrix_bytes,
            independent_equal_tag_entries_per_slice=self.entries//self.slices,
            independent_equal_tag_capacity_bytes=(self.entries//self.slices)*self.slice_data_bytes,
            contract='One common slot/LRU/pin ownership per matrix, derived addresses and paid valid/fill masks; '
                'no independent slice eviction or partial-hit policy. Exact same-order whole-matrix residency capacity, '
                'not a prediction of cache traffic under changed execution. Ports, active frame associations, clocks and macro area unclosed.')

    def compile(self):raise ValueError('Directory cost contract only; banking/ports/frame association are not implemented')


@dataclass(frozen=True)
class VerticalStreamContract:
    ready_granule_bytes: int
    fifo_bytes: int = 64
    descriptor_bytes: int = 4096
    native_atom_bytes: int = 16
    slice_data_bytes: int = 65536
    coupled_frames_per_neighborhood: int = 2
    slices_per_neighborhood: int = 8
    additional_staging_bytes: int = 0

    def __post_init__(self):
        for name,v in asdict(self).items():
            if type(v) is not int or v<(0 if name=='additional_staging_bytes' else 1):
                raise ValueError('Finite integer stream state/storage required')
        if (self.native_atom_bytes!=16 or self.ready_granule_bytes not in (32,4096) or
                self.descriptor_bytes!=4096 or self.slice_data_bytes%self.ready_granule_bytes or
                self.fifo_bytes%self.native_atom_bytes or self.additional_staging_bytes%self.native_atom_bytes):
            raise ValueError('Declare the supported atom, descriptor and readiness layout')
        if self.fifo_bytes+self.additional_staging_bytes<self.ready_granule_bytes:
            raise ValueError('Opaque operand readiness cannot fit in the declared receiver holding storage')

    def record(self):
        prefix=ceil((self.slice_data_bytes//self.ready_granule_bytes)/8)+8
        return dict(**asdict(self),executable=False,prefix_bytes_per_active_slice=prefix,
            prefix_bytes_per_neighborhood=prefix*self.slices_per_neighborhood*self.coupled_frames_per_neighborhood,
            requires_staging_read=self.additional_staging_bytes>0,
            bypass_requires='X/H and original scales ready, real PE grant and retention-write acceptance; '
                'otherwise defer fetch or pay spill/staging and subsequent read. Native return reservations remain separate.',
            contract='Minimum holding and prefix metadata, not a sufficiency proof for out-of-order returns or backpressure. '
                '4096-byte readiness retains a staging read; 32-byte readiness changes the operand interface. '
                'No new issue contexts, independent MAC grants, clocks or free cache-fill path.')

    def compile(self):raise ValueError('Stream contract only; finite tee/credit/reordering/PE protocol is not executable')
