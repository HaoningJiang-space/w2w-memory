"""Bounded message identities; payload contents are represented by byte identity."""
from dataclasses import dataclass

TRAFFIC_CLASSES = ('activation', 'request', 'response')


@dataclass(frozen=True)
class Packet:
    id: str
    src: str
    dst: str
    traffic_class: str
    payload_bytes: int
    route: tuple[str, ...]


@dataclass(frozen=True)
class MemoryRequest:
    id: str
    task: str
    requester: str
    memory: str
    bank: int
    word_address: int
    size_bytes: int = 32
    operation: str = 'READ'
    object_id: str | None = None
    object_offset: int = 0

    def __post_init__(self):
        if self.operation != 'READ' or self.size_bytes < 32 or self.size_bytes % 32:
            raise ValueError('A READ descriptor must contain positive whole 32-byte native words')
