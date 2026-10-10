"""One-domain native frontend/Gateway, with the original external service API.

This intentionally rejects larger machines. It hides internal clock work, not
NoC receive/commit events or descriptor admission. Full evidence stays full.
"""
from w2w.backends.ramulator.adapter import VerticalRWDL
from w2w.backends.ramulator.hbm2 import load_bridge


class NativeMemoryIsland(VerticalRWDL):
    internal_clock_service=True

    def __init__(self,spec,*,backend):
        if (len(spec.stack.dram_domains)!=1 or len(spec.stack.gateways)!=1
                or len(spec.memories)!=1 or spec.memories[0].banks!=1
                or spec.stack.external_ports or spec.noc_period_ps!=1000
                or spec.dram_period_ps!=3760 or spec.flit_bytes!=128 or spec.header_bytes!=16):
            raise ValueError('Memory island requires the registered one-domain/one-Gateway machine')
        if backend.domain_count!=1 or backend.native_cycle or backend.pending:
            raise ValueError('Island requires a fresh one-domain native backend')
        super().__init__(spec,backend=backend,request_control=True)
        bridge,_=load_bridge();constructor=getattr(bridge,'MemoryServiceIsland',None)
        if constructor is None:raise ValueError('Build the reviewed memory-island bridge')
        gateway=spec.stack.gateways[0];domain=spec.stack.dram_domains[0];path=spec.stack.collection_paths[0]
        self.impl=constructor(backend.impl,dict(dram=3760,logic=1000,transport=path.delay_ps,
            pipeline=path.pipeline_cycles,cdc=gateway.cdc_cycles,access=gateway.router_access_cycles,
            return_atoms=domain.return_atoms,slots=spec.memories[0].transaction_slots,
            tx_limit=self.tx_limits[gateway.id],window=spec.stack.native_policy.descriptor_window,
            policy=spec.stack.native_policy.descriptor_policy,gateway_atoms=gateway.data_bytes_per_cycle//16,
            flit_bytes=128,header_bytes=16))
        self.identities={};self.names={};self.history={};self.host_advances=0
        self.next_internal_ps=0;self.native_advances=0

    def submit(self,req,now):
        if now%self.period_ps:return False
        if (req.memory!=self.spec.memories[0].id or req.bank!=0 or req.operation!='READ'
                or req.id in self.identities or not 0<req.size_bytes<=self.spec.memory_request_bytes
                or req.size_bytes%32):raise ValueError('Invalid island descriptor')
        if now!=self.last_ps:raise ValueError('Advance island before external input')
        channel,address=self.address(req,0)
        identity=len(self.identities)
        if not self.impl.submit(identity,req.size_bytes,address,now):return False
        self.identities[req.id]=identity;self.names[identity]=req.id;self.history[req.id]=req
        # A submitted command may add an earlier frontend boundary. Taking one
        # conservative native call next time refreshes that certificate.
        self.next_internal_ps=now
        return True

    def _advance(self,now,until):
        if now<self.last_ps:raise ValueError('Nonmonotonic island time')
        self.host_advances+=1
        if not until and self.last_ps<=now<self.next_internal_ps:
            self.last_ps=now;self.ready_times=[]
            return now,[]
        row=self.impl.advance(now,until);self.last_ps=row['stop_ps'];self.native_advances+=1
        self.next_internal_ps=row['next_internal_ps']
        self.ready.extend((self.names[key],offset,16) for key,offset,at in row['ready'])
        self.ready_times=[(self.names[key],offset,at) for key,offset,at in row['ready']]
        self.native_events.extend(self._event(event) for event in row['events'])
        return row['stop_ps'],[self.names[key] for key in row['complete']]

    def advance(self,now):return self._advance(now,False)[1]

    def advance_until(self,external_limit):
        """Never runs past the caller's known next input; no future trace input."""
        return self._advance(external_limit,True)

    def _event(self,event):
        at,kind,identity,a,b,c,d,_=event
        key=self.names[identity];domain=self.domain_names[0];g=self.spec.stack.gateways[0].id
        base=dict(time_ps=at,request=key,gateway=g)
        if kind==0:return dict(base,kind='request_gateway_access',bytes=16,end_ps=a,arrival_ps=b)
        base['domain']=domain
        if kind==1:return dict(base,kind='request_control_send',bytes=16,end_ps=a,arrival_ps=b,access_end_ps=c)
        if kind==2:return dict(base,kind='domain_range_issued',ack_ready_ps=a)
        if kind==3:return dict(base,kind='request_ack_send',bytes=8,end_ps=a,arrival_ps=b,issued_ps=c,ready_ps=d)
        if kind in (4,5,6):return dict(base,kind={4:'request_ack_arrive',5:'request_control_arrive',6:'domain_descriptor_begin'}[kind])
        if kind in (7,8):return dict(base,kind='array_first_ready' if kind==7 else 'array_last_ready',hb_tail_ps=a)
        raise RuntimeError('Unknown native island evidence kind')

    def compute_epoch_quiescent(self):return False
    def first_callback_boundary(self,*_):return None

    def record(self):
        r=self.impl.ledger();g=self.spec.stack.gateways[0].id;pool=self.spec.memories[0].mc_pool_id
        self.backend.accepted=r['atoms'];self.backend.completed=r['raw_atoms'];self.backend.rejected=r['rejected']
        self.backend.pending=set(range(r['pending_atoms']));self.backend.native_cycle=r['dram_ticks']
        self.accepted=r['accepted'];self.completed=r['completed'];self.reserved[0]=r['reserved']
        for target,field in ((self.reservation_peak,'reservation_peak'),(self.channel_atoms,'atoms'),
                (self.domain_descriptor_peak,'descriptor_peak')):
            if r[field]:target[0]=r[field]
        for target,field in ((self.aggregate_bytes,'gateway_bytes'),(self.aggregate_busy_cycles,'gateway_busy'),
                (self.aggregate_peak,'gateway_peak'),(self.command_peak,'command_peak'),(self.ack_peak,'ack_peak'),
                (self.command_bytes,'command_bytes'),(self.ack_bytes,'ack_bytes')):
            if r[field]:target[g]=r[field]
        if r['pool_peak']:self.pool_peak[pool]=r['pool_peak']
        self.command_live[g]=r['command_live'];self.domain_descriptors[0]=r['descriptors'];self.ack_pending[g]=r['ack_pending']
        self.command_stalls=r['command_stalls'];self.queue_stalls=r['queue_stalls'];self.reservation_stalls=r['reservation_stalls']
        self.native_first_ps=r['first_tail'] or None;self.native_last_ps=r['last_tail'] or None
        self.collection_atom_ps=r['collection_ps'];self.cdc_atom_ps=r['cdc_ps'];self.gateway_atom_ps=r['gateway_ps']
        record=super().record();record['pending']=r['pending']
        return record

    def coordination_record(self):
        r=self.impl.ledger()
        return dict(schema=1,kind='one_domain_native_memory_service',
            host_advances=self.host_advances,native_advances=self.native_advances,internal_frontend_steps=r['steps'],dram_ticks=r['dram_ticks'],
            contract='original internal clock union; callbacks, finite reservations, control and Gateway native; all NoC and external descriptor boundaries retained')
