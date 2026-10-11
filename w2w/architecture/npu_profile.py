"""Concrete reference array/ports within the existing aggregate V3 budget.

    Geometry, banking and local fanout are declared modeling assumptions, not a
    silicon calibration. Local buffers and partials are charged to existing SRAM.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class NPUProfile:
    rows: int = 16
    columns: int = 16
    arrays: int = 64
    weight_read_bytes_per_cycle: int = 32768
    activation_read_bytes_per_cycle: int = 32768
    output_write_bytes_per_cycle: int = 32768
    vector_ops_per_cycle: int = 4096
    banks: int = 128
    bank_port_bytes_per_cycle: int = 256
    word_bytes: int = 32
    input_broadcast_fanout: int = 64
    period_ps: int = 1000
    dataflow: str = 'output_stationary'

    def __post_init__(self):
        for k,v in vars(self).items():
            if k!='dataflow' and (type(v) is not int or v<1):raise ValueError('Finite positive NPU resources required')
        if self.dataflow!='output_stationary' or self.word_bytes!=32:
            raise ValueError('Reference policy has explicit OS and 32 B SRAM words')
        if self.input_broadcast_fanout>self.arrays:raise ValueError('Fanout exceeds array receivers')

    @property
    def macs_per_cycle(self):return self.rows*self.columns*self.arrays

    @property
    def context_buffer_bytes(self):
        return self.arrays*(self.rows*self.columns*4+(self.rows+self.columns)*self.word_bytes+32)

    def validate_cluster(self,cluster):
        p=cluster.profile
        if (self.macs_per_cycle!=p.macs_per_cycle or self.period_ps!=p.period_ps
                or self.weight_read_bytes_per_cycle>p.weight_read_bytes_per_cycle
                or self.activation_read_bytes_per_cycle>p.activation_read_bytes_per_pe_cycle*p.pe_count
                or self.output_write_bytes_per_cycle>p.sram_write_bytes_per_pe_cycle*p.pe_count
                or self.vector_ops_per_cycle>p.vector_ops_per_cycle):
            raise ValueError('NPU shape/ports exceed the original cluster resources')


def reference_profile(array_size=16):
    if array_size not in (16,32):raise ValueError('Registered equal-peak array sizes are 16/32')
    return NPUProfile(rows=array_size,columns=array_size,arrays=16384//array_size**2,
        input_broadcast_fanout=16384//array_size**2)
