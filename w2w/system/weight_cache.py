"""Finite matrix residency, LRU eviction and pins; no future-trace lookahead."""
from collections import Counter,OrderedDict
from dataclasses import dataclass


@dataclass(frozen=True)
class WeightCacheConfig:
    data_bytes_per_cluster: int = 184*1024**2
    entries_per_cluster: int = 512
    metadata_bits_per_entry: int = 128
    lookup_slots_per_cluster: int = 32
    lookup_cycles: int = 1
    initial_resident: tuple = ()  # (cluster, object), explicit warm-start condition

    @property
    def metadata_bytes_per_cluster(self):return self.entries_per_cluster*self.metadata_bits_per_entry//8+self.lookup_slots_per_cluster*12+16


class WeightCache:
    def __init__(self,config,tiles,log):
        if (config.data_bytes_per_cluster<1 or config.entries_per_cluster<1
                or config.metadata_bits_per_entry<128 or config.metadata_bits_per_entry%8
                or config.lookup_cycles<1 or config.lookup_slots_per_cluster<1):
            raise ValueError('Finite cache data and tag/pin/LRU metadata required')
        self.config=config;self.log=log;self.entries={t:OrderedDict() for t in tiles}
        self.used=Counter();self.peak=Counter();self.stats=Counter();self.by_tile=Counter()
        self.initial_bytes=0
        self.ever_seen=set();self.lookup_pending=Counter();self.lookup_free=Counter();self.lookup_times={}

    def acquire(self,tile,key,size,task,now,period):
        entries=self.entries[tile]
        if self.lookup_pending[tile]>=self.config.lookup_slots_per_cluster:return None
        if size>self.config.data_bytes_per_cluster:raise ValueError('Matrix exceeds declared weight-cache partition')
        if key in entries:
            entry=entries[key]
            if not entry['valid']:return None
            entries.move_to_end(key);entry['pins']+=1;hit=True
        else:
            used=self.used[tile];count=len(entries);victims=[]
            for victim,entry in entries.items():
                if used+size<=self.config.data_bytes_per_cluster and count<self.config.entries_per_cluster:break
                if entry['pins']:continue
                victims.append(victim);used-=entry['size'];count-=1
            if used+size>self.config.data_bytes_per_cluster or count>=self.config.entries_per_cluster:return None
            for victim in victims:
                entry=entries.pop(victim);self.used[tile]-=entry['size']
                self.stats['evictions']+=1;self.stats['evicted_bytes']+=entry['size']
                self.log('cache_evict',tile=tile,object=victim,bytes=entry['size'],task=task)
            entries[key]=dict(size=size,valid=False,pins=1);self.used[tile]+=size;hit=False
            self.peak[tile]=max(self.peak[tile],self.used[tile])
        seen=(tile,key) in self.ever_seen
        if not hit:self.stats['reload_bytes' if seen else 'compulsory_bytes']+=size
        self.ever_seen.add((tile,key))
        self.lookup_pending[tile]+=1
        ready=max(now,self.lookup_free[tile])+self.config.lookup_cycles*period
        self.lookup_free[tile]=ready;self.lookup_times[task]=ready
        self.stats['hits' if hit else 'misses']+=1
        self.stats['hit_bytes' if hit else 'miss_bytes']+=size
        self.by_tile[tile,'hit_bytes' if hit else 'miss_bytes']+=size
        self.log('cache_lookup',tile=tile,object=key,task=task,bytes=size,hit=hit,previously_resident=seen,available_ps=ready)
        return hit

    def preload(self,tile,key,size):
        entries=self.entries[tile]
        if (key in entries or self.used[tile]+size>self.config.data_bytes_per_cluster
                or len(entries)>=self.config.entries_per_cluster):raise ValueError('Initial resident set exceeds distributed cache budget')
        entries[key]=dict(size=size,valid=True,pins=0);self.used[tile]+=size;self.initial_bytes+=size
        self.ever_seen.add((tile,key))
        self.peak[tile]=max(self.peak[tile],self.used[tile])
        self.log('cache_initial_resident',tile=tile,object=key,bytes=size)

    def filled(self,tile,key,task):
        entry=self.entries[tile][key]
        if entry['valid'] or not entry['pins']:raise ValueError('Repeated/unowned cache fill')
        entry['valid']=True;self.entries[tile].move_to_end(key)
        self.log('cache_fill',tile=tile,object=key,bytes=entry['size'],task=task)

    def release(self,tile,key):
        entry=self.entries[tile][key]
        if not entry['valid'] or not entry['pins']:raise ValueError('Unfilled cache object released')
        entry['pins']-=1

    def lookup_complete(self,tile,task):
        self.lookup_pending[tile]-=1;del self.lookup_times[task]

    def record(self):
        if any(self.lookup_pending.values()) or any(e['pins'] or not e['valid'] for entries in self.entries.values() for e in entries.values()):
            raise ValueError('Cache finishes with live fills/pins')
        return dict(data_bytes_per_cluster=self.config.data_bytes_per_cluster,
            metadata_bytes_per_cluster=self.config.metadata_bytes_per_cluster,
            entries_per_cluster=self.config.entries_per_cluster,policy='matrix LRU; filling and in-use objects pinned',
            lookup_slots_per_cluster=self.config.lookup_slots_per_cluster,lookup_cycles=self.config.lookup_cycles,
            stats=dict(self.stats),per_cluster={t:{kind:self.by_tile[t,kind] for kind in ('hit_bytes','miss_bytes')} for t in self.entries},
            peak_data_bytes=dict(self.peak),resident_bytes=dict(self.used),
            initial_resident_bytes=self.initial_bytes,
            initialization='warm-start bytes were loaded before measured interval; initialization is not free and is reported separately',
            fill_contract='miss writes directly into reserved cache SRAM via shared receive write port; hit reads share compute SRAM/MAC budgets')
