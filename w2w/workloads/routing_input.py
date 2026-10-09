"""Frozen token selection contains no machine owners or endpoint IDs."""
import json
from pathlib import Path
from .moe import build_moe


def load_workload(path):
    record=json.loads(Path(path).read_text())
    if record['schema']!='w2w.frozen-routing.v3':raise ValueError('Unknown routing input schema')
    return build_moe(record['token_experts'],name=record['name'],**record['shape'],
        partitions=record['partitions'],source_identity=tuple(sorted(record['source_hashes'].items())))
