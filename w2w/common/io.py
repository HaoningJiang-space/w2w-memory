"""JSON I/O with the existing cohort gzip fallback and runner text encoding."""
import gzip
import json
from pathlib import Path


def read_json(path):
    path=Path(path)
    if not path.exists() and path.suffix!='.gz':path=path.with_suffix(path.suffix+'.gz')
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)


def write_json(path,value):
    Path(path).write_text(json.dumps(value,indent=2)+'\n')
