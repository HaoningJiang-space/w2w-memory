"""Modern observation IR over the existing complete, SHA-bound capture reader."""
from dataclasses import dataclass
from .moe_trace import file_sha
from w2w.common.fingerprints import digest_read_v1 as digest
import gzip, json


@dataclass(frozen=True)
class RoutingObservation:
    request_id: str
    phase: str
    token_position: int
    decode_step: int | None
    layer_id: str
    expert_ids: tuple[int, ...]
    source_id: str
    routing_scores: tuple | None = None
    arrival_ps: int | None = None

    @property
    def token_id(self):
        return (self.request_id, self.phase, self.token_position, self.decode_step)


def observations(capture,phase,layer,step=None):
    if phase=='prefill' and step is None:
        rows=capture['prefill'][layer]
        positions=range(len(rows))
    elif phase=='decode' and type(step) is int and 0<=step<capture['coverage']['decode_tokens']:
        rows=(capture['decode'][layer][step],)
        positions=(capture['coverage']['prefill_tokens']+step,)
    else:raise ValueError('Explicit original phase/layer/step required')
    return tuple(RoutingObservation(capture['request_id'],phase,p,step,layer,tuple(row),capture['raw_sha256'])
                 for p,row in zip(positions,rows))


def load_corpus(corpus):
    manifest=json.loads((corpus/'manifest.json').read_text())
    proof=json.loads((corpus/'coverage-audit.json').read_text())
    if not proof['passed'] or file_sha(corpus/'manifest.json')!=proof['normalized_manifest_sha256']:
        raise ValueError('Independently audited complete corpus required')
    for row in manifest['requests']:
        path=corpus/row['path']
        if file_sha(path)!=row['file_sha256']:raise ValueError('Original captured request changed')
        with gzip.open(path,'rt') as f:capture=json.load(f)
        if digest(capture)!=row['normalized_sha256']:raise ValueError('Original routing identity changed')
        yield capture
