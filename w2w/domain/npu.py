"""Mathematical GEMM shape carries no fitted execution duration."""
from dataclasses import dataclass


@dataclass(frozen=True)
class GemmKernel:
    operation_id: str
    M: int
    N: int
    K: int
    weight_object: str
    input_dtype: str = 'BF16'
    weight_dtype: str = 'FP8_E4M3FN'
    accumulator_dtype: str = 'FP32'
    scale_group: tuple = (128,128)
    cached_weights: bool = False

    def __post_init__(self):
        if any(type(x) is not int or x<1 for x in (self.M,self.N,self.K)):
            raise ValueError('Actual positive GEMM dimensions required')
        if type(self.cached_weights) is not bool:raise ValueError('Explicit finite-cache ownership required')
        if (self.input_dtype!='BF16' or self.weight_dtype not in ('FP8_E4M3FN','BF16')
                or self.accumulator_dtype!='FP32' or self.scale_group!=(128,128)):
            raise ValueError('Explicit reference precision/scale contract required')

    @property
    def macs(self):return self.M*self.N*self.K

    @property
    def weight_bytes(self):return self.N*self.K*(1 if self.weight_dtype=='FP8_E4M3FN' else 2)
