"""One physical native ledger shared by every vertical access view.

Ramulator owns commands/rows/refresh. This adapter owns finite reservations,
collection, HB-tail timestamps, CDC and gateway output. No memory-wafer router.
"""
from collections import Counter,defaultdict,deque
from types import SimpleNamespace
import heapq


class VerticalRWDL:
    boundary='controller_payload_ready_after_native_bus'
    streaming=True
    stream_origin='home_controller'
    atomic_bytes=16

    def __init__(self,spec,*,refresh=True,backend=None):
        from w2w.service.dram.rwdl import RamulatorRWDL
        self.spec=spec;self.stack=spec.stack
        self.domains={d.id:d for d in self.stack.dram_domains}
        self.channels={key:i for i,key in enumerate(self.domains)}
        self.domain_names=tuple(self.domains)
        self.interfaces={m.id:m for m in spec.memories}
        self.gateways={g.id:g for g in (*self.stack.gateways,*self.stack.external_ports)}
        self.paths={(p.domain_id,p.gateway_id):p for p in self.stack.collection_paths}
        periods={d.period_ps for d in self.domains.values()};capacities={d.capacity_bytes for d in self.domains.values()}
        if len(periods)!=1 or len(capacities)!=1:raise ValueError('First native backend requires one array clock/capacity')
        self.period_ps=next(iter(periods));self.capacity=next(iter(capacities))
        p=self.stack.native_policy
        timing={k:v for k,v in vars(p).items() if k.startswith('n')}
        profile=SimpleNamespace(controller=p,timing=SimpleNamespace(**timing))
        self.backend=backend if backend is not None else RamulatorRWDL(len(self.stack.memory_regions),
            domain_count=len(self.domains),array_bytes=self.capacity,profile=profile,refresh=refresh)
        self.groups={};self.queues=defaultdict(deque);self.tickets={};self.future=[]
        self.aggregate=defaultdict(deque);self.serial=0;self.ready=[];self.native_events=[]
        self.reserved=Counter();self.reservation_peak=Counter();self.pool_live=Counter();self.pool_peak=Counter()
        self.selected_row={};self.round_robin=Counter();self.last_ps=-1
        self.accepted=self.completed=self.reservation_stalls=self.queue_stalls=0
        self.aggregate_bytes=Counter();self.aggregate_busy_cycles=Counter();self.aggregate_peak=Counter()
        self.channel_atoms=Counter();self.native_first_ps=self.native_last_ps=None
        self.collection_atom_ps=self.cdc_atom_ps=self.gateway_atom_ps=0

    def address(self,req,offset):
        memory=self.interfaces[req.memory]
        word=req.word_address*memory.banks+req.bank+offset//32
        domain=memory.domain_ids[word%memory.banks]
        atom=2*(word//memory.banks)+(offset%32)//16
        if not 0<=atom<self.domains[domain].capacity_bytes//16:
            raise ValueError('Read exceeds physical native domain')
        return self.channels[domain],atom

    def submit(self,req,now):
        if now%self.period_ps:return False
        memory=self.interfaces[req.memory]
        if req.id in self.groups or not 0<req.size_bytes<=self.spec.memory_request_bytes or req.size_bytes%32:
            raise ValueError('Invalid native descriptor')
        if not 0<=req.bank<memory.banks:raise ValueError('Invalid logical bank')
        if self.pool_live[memory.mc_pool_id]>=memory.transaction_slots:return False
        cursors={self.channels[d]:((i-req.bank)%memory.banks)*32 for i,d in enumerate(memory.domain_ids)}
        row=dict(request=req,cursors=cursors,completed=0,raw_completed=0)
        self.groups[req.id]=row
        for channel,offset in cursors.items():
            if offset<req.size_bytes:self.queues[channel].append(req.id)
        self.pool_live[memory.mc_pool_id]+=1
        self.pool_peak[memory.mc_pool_id]=max(self.pool_peak[memory.mc_pool_id],self.pool_live[memory.mc_pool_id])
        self.accepted+=1
        return True

    def _schedule(self,at,kind,key,offset,channel,origin):
        self.serial+=1;heapq.heappush(self.future,(at,self.serial,kind,key,offset,channel,origin))

    def advance(self,now):
        if now<self.last_ps:raise ValueError('Nonmonotonic native time')
        self.last_ps=now
        for ticket,cycle in self.backend.advance(now):
            key,offset,channel=self.tickets.pop(ticket);row=self.groups[key]
            at=cycle*self.period_ps;memory=self.interfaces[row['request'].memory]
            gateway=self.gateways[memory.gateway_id]
            domain=self.domain_names[channel]
            path=self.paths.get((domain,memory.gateway_id))
            # External service is an off-wafer proxy with a declared edge link;
            # its shared gateway throughput, rather than a vertical lane, limits I/O.
            transport=path.delay_ps if path is not None else 20000
            if path is None and memory.gateway_id not in {p.id for p in self.stack.external_ports}:
                raise RuntimeError('Missing physical vertical path')
            hb_tail=at+transport
            cdc=getattr(gateway,'cdc_cycles',2)
            sample=((hb_tail+self.spec.noc_period_ps-1)//self.spec.noc_period_ps+cdc)*self.spec.noc_period_ps
            self.collection_atom_ps+=transport;self.cdc_atom_ps+=sample-hb_tail
            row['raw_completed']+=1
            if row['raw_completed'] in (1,row['request'].size_bytes//16):
                self.native_events.append(dict(time_ps=at-self.period_ps,
                    kind='array_first_ready' if row['raw_completed']==1 else 'array_last_ready',
                    request=key,domain=domain,hb_tail_ps=hb_tail,gateway=memory.gateway_id))
            self.native_first_ps=at if self.native_first_ps is None else self.native_first_ps
            self.native_last_ps=at
            self._schedule(sample,'collect',key,offset,channel,at)
        completed=[]
        if now%self.spec.noc_period_ps==0:
            while self.future and self.future[0][0]<=now:
                at,_,kind,key,offset,channel,origin=heapq.heappop(self.future)
                row=self.groups[key];memory=self.interfaces[row['request'].memory]
                if kind=='collect':
                    q=self.aggregate[memory.gateway_id];q.append((key,offset,channel,at,origin))
                    self.aggregate_peak[memory.gateway_id]=max(self.aggregate_peak[memory.gateway_id],len(q)*16)
                else:
                    self.reserved[channel]-=1;self.ready.append((key,offset,16));row['completed']+=1
                    self.gateway_atom_ps+=at-origin
                    if row['completed']*16==row['request'].size_bytes:
                        completed.append(key);self.pool_live[memory.mc_pool_id]-=1
                        del self.groups[key];self.completed+=1
            for key,queue in self.aggregate.items():
                gateway=self.gateways[key];count=min(len(queue),gateway.data_bytes_per_cycle//16)
                if count:self.aggregate_busy_cycles[key]+=1
                for _ in range(count):
                    req,offset,channel,at,origin=queue.popleft();self.aggregate_bytes[key]+=16
                    delay=(1+getattr(gateway,'router_access_cycles',64))*self.spec.noc_period_ps
                    self._schedule(now+delay,'payload',req,offset,channel,origin)
        if now%self.period_ps==0:
            domain_list=list(self.domains.values());p=self.stack.native_policy
            for channel,queue in self.queues.items():
                if not queue:continue
                if self.reserved[channel]>=domain_list[channel].return_atoms:
                    self.reservation_stalls+=1;continue
                index=0;window=min(p.descriptor_window,len(queue))
                if p.descriptor_policy=='round_robin':index=self.round_robin[channel]%window
                elif p.descriptor_policy=='row_batched' and channel in self.selected_row:
                    for i in range(window):
                        row=self.groups[queue[i]]
                        _,a=self.address(row['request'],row['cursors'][channel])
                        if a//64==self.selected_row[channel]:index=i;break
                key=queue[index];row=self.groups[key];req=row['request'];offset=row['cursors'][channel]
                mapped,address=self.address(req,offset)
                if mapped!=channel:raise RuntimeError('Physical domain mapping changed')
                ticket=self.backend.submit(channel,address)
                if ticket is None:self.queue_stalls+=1;continue
                self.tickets[ticket]=(key,offset,channel);self.reserved[channel]+=1
                self.reservation_peak[channel]=max(self.reservation_peak[channel],self.reserved[channel])
                self.channel_atoms[channel]+=1;self.selected_row[channel]=address//64
                self.round_robin[channel]=(index+1)%p.descriptor_window
                offset+=16 if offset%32==0 else self.interfaces[req.memory].banks*32-16
                row['cursors'][channel]=offset
                if offset>=req.size_bytes:queue.remove(key)
        return completed

    def take_ready(self):
        ready,self.ready=self.ready,[];return ready

    def take_native_events(self):
        events,self.native_events=self.native_events,[];return events

    def record(self):
        record=self.backend.record()
        record.update(kind='ramulator_vertical_domains_v3',boundary=self.boundary,streaming=True,
            physical_domain_count=len(self.domains),physical_capacity_bytes=sum(d.capacity_bytes for d in self.domains.values()),
            grouped_descriptors_accepted=self.accepted,grouped_descriptors_completed=self.completed,
            pending=len(self.groups)+len(self.tickets)+len(self.future)+sum(map(len,self.aggregate.values())),
            reservations_live=sum(self.reserved.values()),reservation_peak_atoms=dict(self.reservation_peak),
            channel_atoms=dict(self.channel_atoms),gateway_bytes=dict(self.aggregate_bytes),
            gateway_busy_cycles=dict(self.aggregate_busy_cycles),gateway_queue_peak_bytes=dict(self.aggregate_peak),
            native_first_tail_ps=self.native_first_ps,native_last_tail_ps=self.native_last_ps,
            reservation_stall_attempts=self.reservation_stalls,queue_stall_attempts=self.queue_stalls,
            collection_atom_ps=self.collection_atom_ps,cdc_atom_ps=self.cdc_atom_ps,
            gateway_total_atom_ps=self.gateway_atom_ps,pool_peak=dict(self.pool_peak),
            scope='physical native domains counted once; finite reservations through physical transport; assumed array timing')
        return record

    def close(self):self.backend.close()
