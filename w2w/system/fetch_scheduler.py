"""Finite matrix admission and shared descriptor issue, owned by one controller."""
from collections import Counter


class FetchScheduler:
    def __init__(self,host,contexts,policy,return_contexts=0):
        self.host=host;self.contexts=contexts;self.policy=policy
        self.live={tile:set() for tile in host.builder.tiles};self.peak=Counter();self.cursor={}
        self.metadata_bytes=64*contexts+8 if contexts else 0
        self.returns=None
        if return_contexts:
            from .return_tracker import ReturnTracker
            self.returns=ReturnTracker(host,return_contexts)

    def can_allocate(self,tile):
        return (not self.contexts or len(self.live[tile])<self.contexts) and (self.returns is None or self.returns.can_allocate(tile))

    def acquire(self,key):
        if not self.contexts:return
        tile=self.host.tasks[key].tile
        self.live[tile].add(key);self.peak[tile]=max(self.peak[tile],len(self.live[tile]))
        self.host.log('fetch_context_acquire',task=key,tile=tile)
        if self.returns:self.returns.acquire(key)

    def complete(self,key):
        if not self.contexts:return
        h=self.host;tile=h.tasks[key].tile
        if self.returns:
            if key in self.live[tile]:self.issue_complete(key)
            self.returns.complete(key)
            return
        if key in self.live[tile]:
            self.live[tile].remove(key);h.reading.discard(key);h.state[key]['issued_all']=True
            h.log('fetch_context_release',task=key,tile=tile)

    def issue_complete(self,key):
        if not self.returns:return
        h=self.host;tile=h.tasks[key].tile
        self.returns.issue_done(key)
        h.state[key]['issued_all']=True;h.reading.discard(key)
        self.live[tile].remove(key)
        h.log('fetch_context_release',task=key,tile=tile)

    def return_commit(self,request):
        if self.returns:self.returns.commit(request)

    def bind(self,req):
        if self.returns:self.returns.bind(req)

    def issue(self):
        if self.policy=='round_robin':return self.round_robin()
        h=self.host;used=Counter()
        for key in sorted(h.reading):
            task,state=h.tasks[key],h.state[key]
            if (not state['allocated'] or key in h.cache_waiting or state['issued_all'] or
                    used[task.tile]>=h.spec.read_requests_per_tile_cycle or h.outstanding[task.tile]>=h.spec.outstanding_per_tile):
                continue
            while used[task.tile]<h.spec.read_requests_per_tile_cycle and h.outstanding[task.tile]<h.spec.outstanding_per_tile:
                if state['next_read'] is None:state['next_read']=next(state['iterator'],None)
                req=state['next_read']
                if req is None:
                    state['issued_all']=True;h.reading.remove(key);self.issue_complete(key);break
                mc=h.builder.memories[req.memory].home_tile
                if not h._send(req.id+'/req',task.tile,mc,'request',0,'request',req.id):break
                h.requests[req.id]=dict(request=req,stage='request_flight');state['next_read']=None
                self.bind(req)
                h.outstanding[task.tile]+=1;h.outstanding_peak[task.tile]=max(h.outstanding_peak[task.tile],h.outstanding[task.tile])
                used[task.tile]+=1
                h.log('read_issue',request=req.id,task=key,memory=req.memory,bank=req.bank,word_address=req.word_address,bytes=req.size_bytes)

    def round_robin(self):
        h=self.host
        for tile in sorted(self.live):
            used=0
            while used<h.spec.read_requests_per_tile_cycle and h.outstanding[tile]<h.spec.outstanding_per_tile:
                candidates=sorted(k for k in self.live[tile] if k in h.reading and k not in h.cache_waiting)
                cursor=self.cursor.get(tile,'');candidates=[k for k in candidates if k>cursor]+[k for k in candidates if k<=cursor]
                progressed=False
                for key in candidates:
                    state=h.state[key]
                    if state['next_read'] is None:state['next_read']=next(state['iterator'],None)
                    req=state['next_read']
                    if req is None:
                        state['issued_all']=True;h.reading.discard(key);self.issue_complete(key);progressed=True;continue
                    mc=h.builder.memories[req.memory].home_tile
                    if not h._send(req.id+'/req',tile,mc,'request',0,'request',req.id):continue
                    h.requests[req.id]=dict(request=req,stage='request_flight');state['next_read']=None
                    self.bind(req)
                    h.outstanding[tile]+=1;h.outstanding_peak[tile]=max(h.outstanding_peak[tile],h.outstanding[tile])
                    self.cursor[tile]=key;used+=1;progressed=True
                    h.log('read_issue',request=req.id,task=key,memory=req.memory,bank=req.bank,word_address=req.word_address,bytes=req.size_bytes)
                    break
                if not progressed:break
