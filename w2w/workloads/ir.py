"""Machine-independent operators and tensor storage identities."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Tensor:
    id: str
    bytes: int
    dtype: str
    producer: str | None
    consumers: tuple[str, ...]
    storage_id: str


@dataclass(frozen=True)
class Operation:
    id: str
    kind: str
    expert: int | None = None
    block: int | None = None
    partition: int | None = None
    token_ids: tuple[int, ...] = ()
    macs: int = 0
    vector_ops: int = 0
    weight_tensors: tuple[str, ...] = ()
    scratch_bytes: int = 0


@dataclass(frozen=True)
class LogicalWorkload:
    name: str
    shape: tuple[int, int, int, int, int]
    tokens: tuple
    operations: tuple[Operation, ...]
    tensors: tuple[Tensor, ...]
    weight_sizes: tuple[tuple[str, int], ...]
    source_identity: tuple = ()
    partitions: int = 4
    schema: str = 'w2w.logical-moe.v3'

    def __post_init__(self):
        ops={o.id:o for o in self.operations}
        if len(ops)!=len(self.operations): raise ValueError('Duplicate logical operation')
        if len({t.id for t in self.tensors})!=len(self.tensors): raise ValueError('Duplicate tensor')
        for t in self.tensors:
            if t.bytes < 1 or t.producer not in (*ops,None) or any(c not in ops for c in t.consumers):
                raise ValueError('Invalid tensor dependency')
