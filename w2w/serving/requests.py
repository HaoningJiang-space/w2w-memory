"""Captured-horizon request lifecycle; arrivals and token values remain modeled/unknown."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ServingRequest:
    request_id:str
    prefill_tokens:int
    decode_steps:int
    raw_sha256:str
    arrival_ps:int=0
    arrival_kind:str='modeled simultaneous admission'

    def __post_init__(self):
        if (not isinstance(self.request_id,str) or not self.request_id
                or any(type(v) is not int or v<1 for v in (self.prefill_tokens,self.decode_steps))
                or type(self.arrival_ps) is not int or self.arrival_ps<0):
            raise ValueError('Explicit request identity, positive captured horizon and integer arrival required')


class RequestLifecycle:
    def __init__(self,requests):
        requests=tuple(requests)
        self.requests={r.request_id:r for r in requests};self.outputs={r.request_id:[] for r in requests}
        if len(self.requests)!=len(requests):raise ValueError('Request identities must remain unique')

    def emit(self,rid,phase,step,time_ps):
        r=self.requests[rid];out=self.outputs[rid]
        if (phase not in ('prefill','decode') or phase=='prefill' and step is not None
                or phase=='decode' and (type(step) is not int or not 0<=step<r.decode_steps)
                or type(time_ps) is not int):
            raise ValueError('Captured phase/step and integer completion time required')
        expected=0 if phase=='prefill' else step+1
        if expected!=len(out) or time_ps<r.arrival_ps or out and time_ps<=out[-1]:
            raise ValueError('Token emission skipped, repeated or violates autoregressive completion')
        out.append(time_ps)

    def metrics(self):
        result={}
        for rid,r in self.requests.items():
            out=self.outputs[rid]
            if len(out)!=r.decode_steps+1:raise ValueError('Incomplete full-model serving horizon; TTFT/TPOT rejected')
            differences=[b-a for a,b in zip(out,out[1:])]
            result[rid]=dict(ttft_ps=out[0]-r.arrival_ps,tpot_ps=sum(differences)/len(differences),
                token_completion_ps=out,decode_intervals_ps=differences,arrival_kind=r.arrival_kind,
                termination='End of captured 128-step horizon; EOS/actual generation length not supplied')
        return result
