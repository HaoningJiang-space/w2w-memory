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

    def __init__(self,spec,*,refresh=True,backend=None,request_control=False,gateway_trace_bin_ps=0):
        from w2w.backends.ramulator.rwdl import RamulatorRWDL
        self.spec=spec;self.stack=spec.stack
        self.domains={d.id:d for d in self.stack.dram_domains}
        self.channels={key:i for i,key in enumerate(self.domains)}
        self.domain_names=tuple(self.domains)
        self.domain_list=tuple(self.domains.values())
        self.interfaces={m.id:m for m in spec.memories}
        self.gateways={g.id:g for g in (*self.stack.gateways,*self.stack.external_ports)}
        self.paths={(p.domain_id,p.gateway_id):p for p in self.stack.collection_paths}
        for port in self.stack.vertical_ports:
            if port.data_bits!=sum(self.domains[d].data_bits for d in port.domain_ids) or port.period_ps!=3760:
                raise ValueError('First vertical backend requires explicitly dedicated RWDL lanes; shared-port SerDes is not implicit')
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
        if type(gateway_trace_bin_ps) is not int or gateway_trace_bin_ps<0 or gateway_trace_bin_ps%spec.noc_period_ps:
            raise ValueError('Gateway evidence bins must be nonnegative integral logic cycles')
        self.gateway_trace_bin_ps=gateway_trace_bin_ps;self.gateway_trace=defaultdict(lambda:defaultdict(Counter))
        self.channel_atoms=Counter();self.native_first_ps=self.native_last_ps=None
        self.collection_atom_ps=self.cdc_atom_ps=self.gateway_atom_ps=0
        self.request_control=request_control
        self.command_free=Counter();self.command_live=Counter();self.command_peak=Counter()
        self.domain_descriptors=Counter();self.domain_descriptor_peak=Counter()
        self.command_bytes=Counter();self.command_stalls=0
        self.access_free=Counter();self.ack_free=Counter();self.ack_pending=Counter();self.ack_peak=Counter()
        self.control_requests={};self.command_started=set();self.ack_bytes=Counter()
        self.tx_limits={g.id:g.descriptor_slots*max((m.banks for m in spec.memories if m.gateway_id==g.id),default=0) for g in self.stack.gateways}
        self.control_ports={p.gateway_id:p for p in self.stack.vertical_ports}
        if request_control:
            if self.stack.external_ports:raise ValueError('External request control needs a separately declared I/O protocol')
            owners=defaultdict(set)
            for p in self.stack.collection_paths:owners[p.domain_id].add(p.gateway_id)
            if any(len(v)!=1 for v in owners.values()):raise ValueError('First control frontend requires one owning gateway/domain')
            if any(p.control_bits!=64 or p.control_period_ps!=spec.noc_period_ps for p in self.stack.vertical_ports):
                raise ValueError('First control path declares 32 forward and 32 reverse bits at the logic clock')

    @staticmethod
    def _edge(at,period):return (at+period-1)//period*period

    def _command(self,req,channel,offset,now,access_end):
        g=self.gateways[self.interfaces[req.memory].gateway_id]
        path=self.paths[self.domain_names[channel],g.id];period=self.control_ports[g.id].control_period_ps
        start=self._edge(max(access_end,self.command_free[g.id]),period);end=start+4*period
        self.command_free[g.id]=end
        arrival=self._edge(end+(1+path.pipeline_cycles)*period+2*self.period_ps,self.period_ps)
        self.command_live[g.id]+=1;self.command_peak[g.id]=max(self.command_peak[g.id],self.command_live[g.id])
        self.domain_descriptors[channel]+=1;self.domain_descriptor_peak[channel]=max(self.domain_descriptor_peak[channel],self.domain_descriptors[channel])
        self.command_bytes[g.id]+=16
        self.native_events.append(dict(time_ps=start,kind='request_control_send',request=req.id,domain=self.domain_names[channel],
            gateway=g.id,bytes=16,end_ps=end,arrival_ps=arrival,access_end_ps=access_end))
        self._schedule(arrival,'command',req.id,offset,channel,now)

    def _ack(self,key,channel,now):
        g=self.gateways[self.control_requests[key]['gateway']];path=self.paths[self.domain_names[channel],g.id]
        period=self.control_ports[g.id].control_period_ps
        # Return credit only after the last atomic request was accepted by the
        # local controller and the finite ACK has traversed the physical path.
        ready=self._edge(now+(1+path.pipeline_cycles)*period,period)
        self._schedule(ready,'ack_ready',key,0,channel,now)
        self.native_events.append(dict(time_ps=now,kind='domain_range_issued',request=key,domain=self.domain_names[channel],gateway=g.id,ack_ready_ps=ready))

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
        active=[channel for channel,offset in cursors.items() if offset<req.size_bytes]
        if self.request_control and (self.command_live[memory.gateway_id]+len(active)>self.tx_limits[memory.gateway_id] or any(self.domain_descriptors[c]>=32 for c in active)):
            self.command_stalls+=1;return False
        # Cache the physical atom at each cursor. Success advances it by one;
        # failed native acceptance leaves both cursor and atom untouched.
        addresses={channel:self.address(req,offset)[1] for channel,offset in cursors.items() if offset<req.size_bytes}
        row=dict(request=req,cursors=cursors,addresses=addresses,completed=0,raw_completed=0)
        self.groups[req.id]=row
        access_end=now
        if self.request_control:
            g=self.gateways[memory.gateway_id];period=self.spec.noc_period_ps
            start=self._edge(max(now,self.access_free[g.id]),period);end=start+2*period
            self.access_free[g.id]=end;access_end=end+g.router_access_cycles*period
            self.control_requests[req.id]=dict(gateway=g.id,left=len(active))
            self.native_events.append(dict(time_ps=start,kind='request_gateway_access',request=req.id,gateway=g.id,
                bytes=16,end_ps=end,arrival_ps=access_end))
        for channel,offset in cursors.items():
            if offset>=req.size_bytes:continue
            if not self.request_control:self.queues[channel].append(req.id)
            else:self._command(req,channel,offset,now,access_end)
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
        while self.future and self.future[0][0]<=now:
            at,_,kind,key,offset,channel,origin=heapq.heappop(self.future)
            if kind in ('ack_ready','command_ack'):
                g=self.gateways[self.control_requests[key]['gateway']];period=self.control_ports[g.id].control_period_ps
                if kind=='ack_ready':
                    self.ack_pending[g.id]+=1;self.ack_peak[g.id]=max(self.ack_peak[g.id],self.ack_pending[g.id])
                    if self.ack_pending[g.id]>self.tx_limits[g.id]:raise RuntimeError('Finite ACK queue exceeded')
                    start=self._edge(max(at,self.ack_free[g.id]),period);end=start+2*period
                    self.ack_free[g.id]=end;arrival=end+2*period;self.ack_bytes[g.id]+=8
                    self.native_events.append(dict(time_ps=start,kind='request_ack_send',request=key,domain=self.domain_names[channel],
                        gateway=g.id,bytes=8,end_ps=end,arrival_ps=arrival,issued_ps=origin,ready_ps=at))
                    self._schedule(arrival,'command_ack',key,0,channel,origin)
                else:
                    self.ack_pending[g.id]-=1;self.command_live[g.id]-=1;self.domain_descriptors[channel]-=1
                    self.control_requests[key]['left']-=1
                    if self.control_requests[key]['left']==0:del self.control_requests[key]
                    self.native_events.append(dict(time_ps=at,kind='request_ack_arrive',request=key,domain=self.domain_names[channel],gateway=g.id))
                continue
            row=self.groups[key];memory=self.interfaces[row['request'].memory]
            if kind=='command':
                self.queues[channel].append(key)
                self.native_events.append(dict(time_ps=at,kind='request_control_arrive',request=key,domain=self.domain_names[channel],gateway=memory.gateway_id))
            elif kind=='collect':
                q=self.aggregate[memory.gateway_id];q.append((key,offset,channel,at,origin))
                self.aggregate_peak[memory.gateway_id]=max(self.aggregate_peak[memory.gateway_id],len(q)*16)
            else:
                self.reserved[channel]-=1;self.ready.append((key,offset,16));row['completed']+=1
                self.gateway_atom_ps+=at-origin
                if row['completed']*16==row['request'].size_bytes:
                    completed.append(key);self.pool_live[memory.mc_pool_id]-=1
                    del self.groups[key];self.completed+=1
        if now%self.spec.noc_period_ps==0:
            for key,queue in self.aggregate.items():
                gateway=self.gateways[key];count=min(len(queue),gateway.data_bytes_per_cycle//16)
                if count:self.aggregate_busy_cycles[key]+=1
                if count and self.gateway_trace_bin_ps:
                    trace=self.gateway_trace[key][now//self.gateway_trace_bin_ps]
                    trace['bytes']+=count*16;trace['busy_cycles']+=1
                for _ in range(count):
                    req,offset,channel,at,origin=queue.popleft();self.aggregate_bytes[key]+=16
                    delay=(1+getattr(gateway,'router_access_cycles',64))*self.spec.noc_period_ps
                    self._schedule(now+delay,'payload',req,offset,channel,origin)
        if now%self.period_ps==0:
            domain_list=self.domain_list;p=self.stack.native_policy
            for channel,queue in self.queues.items():
                if not queue:continue
                if self.reserved[channel]>=domain_list[channel].return_atoms:
                    self.reservation_stalls+=1;continue
                index=0;window=min(p.descriptor_window,len(queue))
                if p.descriptor_policy=='round_robin':index=self.round_robin[channel]%window
                elif p.descriptor_policy=='row_batched' and channel in self.selected_row:
                    for i in range(window):
                        row=self.groups[queue[i]]
                        a=row['addresses'][channel]
                        if a//64==self.selected_row[channel]:index=i;break
                key=queue[index];row=self.groups[key];req=row['request'];offset=row['cursors'][channel]
                address=row['addresses'][channel]
                ticket=self.backend.submit(channel,address)
                if ticket is None:self.queue_stalls+=1;continue
                if self.request_control and (key,channel) not in self.command_started:
                    self.command_started.add((key,channel))
                    self.native_events.append(dict(time_ps=now,kind='domain_descriptor_begin',request=key,domain=self.domain_names[channel],gateway=self.interfaces[req.memory].gateway_id))
                self.tickets[ticket]=(key,offset,channel);self.reserved[channel]+=1
                self.reservation_peak[channel]=max(self.reservation_peak[channel],self.reserved[channel])
                self.channel_atoms[channel]+=1;self.selected_row[channel]=address//64
                self.round_robin[channel]=(index+1)%p.descriptor_window
                offset+=16 if offset%32==0 else self.interfaces[req.memory].banks*32-16
                row['cursors'][channel]=offset
                row['addresses'][channel]+=1
                if offset>=req.size_bytes:
                    queue.remove(key)
                    if self.request_control:
                        self.command_started.remove((key,channel));self._ack(key,channel,now)
        return completed

    def take_ready(self):
        ready,self.ready=self.ready,[];return ready

    def take_native_events(self):
        events,self.native_events=self.native_events,[];return events

    def compute_epoch_quiescent(self):
        """No frontend callback/admission can change before the next mutation.

        This permits fewer host calls, not skipping Ramulator's internal clocks
        or refresh. Unknown backends do not acquire this capability implicitly.
        """
        return (not self.groups and not self.tickets and not self.future
            and not any(self.queues.values()) and not any(self.aggregate.values())
            and not self.ready and not self.native_events and not self.control_requests
            and not self.command_started and not any(self.reserved.values())
            and not any(self.pool_live.values()) and not any(self.command_live.values())
            and not any(self.domain_descriptors.values()) and not any(self.ack_pending.values())
            and hasattr(self.backend,'pending') and not self.backend.pending)

    def record(self):
        record=self.backend.record()
        record['native_service_scope']=record.get('scope')
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
            scope=f'{len(self.domains)} physical {self.capacity*8//1024**2}-Mbit native domains counted once; finite reservations through physical transport; assumed array timing')
        record['request_control']=dict(enabled=self.request_control,command_bytes_per_domain_descriptor=16,
            ack_bytes_per_domain_descriptor=8,tx_limits=dict(self.tx_limits),domain_descriptor_entries=32,
            queue_peak=dict(self.command_peak),domain_queue_peak=dict(self.domain_descriptor_peak),ack_queue_peak=dict(self.ack_peak),
            tx_live=sum(self.command_live.values()),domain_ranges_live=sum(self.domain_descriptors.values()),
            ack_live=sum(self.ack_pending.values()),bytes_by_gateway=dict(self.command_bytes),ack_bytes_by_gateway=dict(self.ack_bytes),admission_stalls=self.command_stalls,
            additional_tx_storage_bytes=16*sum(self.tx_limits.values()) if self.request_control else 0,
            additional_ack_storage_bytes=16*sum(self.tx_limits.values()) if self.request_control else 0,
            additional_domain_descriptor_bytes=512*len(self.domains) if self.request_control else 0,
            control_wire_bit_um=sum(64*p.length_um for p in self.stack.collection_paths) if self.request_control else 0,
            control_pipeline_bits=sum(64*p.pipeline_cycles for p in self.stack.collection_paths) if self.request_control else 0,
            gateway_access_control_wire_bit_um=sum(g.control_bits*sum(abs(a-b) for a,b in zip(g.position_um,next(r for r in self.stack.routers if r.id==g.router_id).position_um)) for g in self.stack.gateways) if self.request_control else 0,
            gateway_access_control_pipeline_bits=sum(g.control_bits*g.router_access_cycles for g in self.stack.gateways) if self.request_control else 0,
            contract='16 B range/domain; shared 32-bit forward and reverse HB control at logic clock; explicit router-to-gateway access, physical domain propagation and CDC; range expanded locally; credits retained through 8 B serialized ACK; bounded queues, native ACT/PRE/RD unchanged')
        if self.gateway_trace_bin_ps:
            record['gateway_service_bins']=dict(interval_ps=self.gateway_trace_bin_ps,
                gateways={key:[dict(start_ps=index*self.gateway_trace_bin_ps,end_ps=(index+1)*self.gateway_trace_bin_ps,**counts)
                    for index,counts in sorted(bins.items())] for key,bins in self.gateway_trace.items()},
                contract='Actual aggregate-output payload/busy cycles in fixed bins; observation only, no service skipped or averaged in execution; empty bins imply zero; last bin can extend beyond drain')
        return record

    def close(self):self.backend.close()
