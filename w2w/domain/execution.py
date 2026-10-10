"""Task IR: control order is distinct from delivered data. No trace fitting or I/O."""
from dataclasses import dataclass
from w2w.common.validators import positive


@dataclass(frozen=True)
class ResidentObject:
    id: str
    memory: str
    offset_bytes: int
    size_bytes: int
    storage_id: str | None = None

    def __post_init__(self):
        positive(self.offset_bytes, 'object offset', 0)
        positive(self.size_bytes, 'object size')
        if self.offset_bytes % 32 or self.size_bytes % 32:
            raise ValueError('Resident objects must be native-word aligned')


@dataclass(frozen=True)
class ReadAccess:
    object_id: str
    offset_bytes: int
    size_bytes: int

    def __post_init__(self):
        positive(self.offset_bytes, 'read offset', 0)
        positive(self.size_bytes, 'read size')
        if self.offset_bytes % 32 or self.size_bytes % 32:
            raise ValueError('Reads must be native-word aligned')


@dataclass(frozen=True)
class StreamGemm:
    weight_object: str
    weight_data_bytes: int
    scale_bytes: int
    macs: int
    macs_per_cycle: int
    weight_read_bytes_per_cycle: int

    def __post_init__(self):
        for name in ('weight_data_bytes','scale_bytes','macs','macs_per_cycle','weight_read_bytes_per_cycle'):
            positive(getattr(self,name),name)
        if self.macs%self.weight_data_bytes:raise ValueError('Integral token reuse required')
        if self.macs//self.weight_data_bytes>self.macs_per_cycle:
            raise ValueError('Streaming primitive requires a smaller explicit token microbatch')


@dataclass(frozen=True)
class ComputeTask:
    id: str
    tile: str
    compute_cycles: int
    reads: tuple[ReadAccess, ...] = ()
    scratch_bytes: int = 0
    release_ps: int = 0
    stream: StreamGemm | None = None

    def __post_init__(self):
        object.__setattr__(self, 'reads', tuple(self.reads))
        for key in ('compute_cycles', 'scratch_bytes', 'release_ps'):
            positive(getattr(self, key), key, 0)


@dataclass(frozen=True)
class ControlEdge:
    producer: str
    consumer: str


@dataclass(frozen=True)
class DataEdge:
    id: str
    producer: str
    consumer: str
    size_bytes: int

    def __post_init__(self):
        positive(self.size_bytes, 'data edge bytes')


@dataclass(frozen=True)
class ExecutionGraph:
    tasks: tuple[ComputeTask, ...]
    objects: tuple[ResidentObject, ...] = ()
    data: tuple[DataEdge, ...] = ()
    control: tuple[ControlEdge, ...] = ()

    def __post_init__(self):
        for key in ('tasks', 'objects', 'data', 'control'):
            object.__setattr__(self, key, tuple(getattr(self, key)))
        for items in (self.tasks, self.objects, self.data):
            ids = [item.id for item in items]
            if len(ids) != len(set(ids)) or any(not key for key in ids):
                raise ValueError('Identifiers must be nonempty and unique')
        if not self.tasks:
            raise ValueError('Execution graph is empty')
        remaining = {t.id: set() for t in self.tasks}
        for edge in (*self.data, *self.control):
            if edge.producer not in remaining or edge.consumer not in remaining:
                raise ValueError('Unknown task in dependency')
            remaining[edge.consumer].add(edge.producer)
        from collections import deque
        followers={key:set() for key in remaining}
        for key,deps in remaining.items():
            for producer in deps:followers[producer].add(key)
        counts={key:len(deps) for key,deps in remaining.items()}
        ready=deque(key for key,count in counts.items() if not count);seen=0
        while ready:
            key=ready.popleft();seen+=1
            for consumer in followers[key]:
                counts[consumer]-=1
                if not counts[consumer]:ready.append(consumer)
        if seen!=len(remaining):raise ValueError('Execution graph contains a cycle; no edges were removed')
