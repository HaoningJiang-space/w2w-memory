"""Array/RWDL -> reserved CDC storage -> shared aggregation -> home MC.

The 4096 RWDL/HB data lanes per memory are ONE physical interface at 3760 ps.
The logic-side aggregate port is 2048 bits/NoC cycle; no direct-return branch.
32 logical bank-interleaved words are retained; each word issues two 16 B reads.
"""
from collections import Counter, defaultdict, deque
import heapq


class RWDLAbsolute:
    boundary = 'controller_payload_ready_after_native_bus'
    streaming = True
    stream_origin = 'home_controller'
    native_ready_location = 'array_digital_rw_dl'
    atomic_bytes = 16
    period_ps = 3760
    cdc_cycles = 2
    reservations_per_channel = 8

    def __init__(self, spec, *, aggregation_bytes_per_cycle=256, refresh=True, command_trace=None,
                 streaming=True,profile=None):
        from w2w.service.dram.rwdl import RamulatorRWDL
        if spec.dram_period_ps != self.period_ps or any(
                m.banks != 32 or m.capacity_bytes != 512*1024**2 for m in spec.memories):
            raise ValueError('RWDL candidate requires 3760 ps and 32 arrays/512 MiB per memory')
        if (type(aggregation_bytes_per_cycle) is not int or aggregation_bytes_per_cycle < 16
                or aggregation_bytes_per_cycle % 16):
            raise ValueError('Aggregation port must contain whole 16 B beats')
        self.spec = spec
        self.profile=profile
        self.descriptor_window=1 if profile is None else profile.controller.descriptor_window
        if profile is not None:
            aggregation_bytes_per_cycle=profile.aggregation.bytes_per_cycle
            self.cdc_cycles=profile.aggregation.cdc_cycles
            self.reservations_per_channel=profile.aggregation.reserved_atoms_per_array
        self.streaming=streaming
        self.backend = RamulatorRWDL(len(spec.memories), refresh=refresh, command_trace=command_trace,profile=profile)
        self.channels = {m.id: i for i,m in enumerate(spec.memories)}
        self.slots = {m.id: m.transaction_slots for m in spec.memories}
        self.aggregation_bytes_per_cycle = aggregation_bytes_per_cycle
        self.groups = {}
        self.queues = defaultdict(deque)
        self.round_robin=Counter()
        self.tickets = {}
        self.reserved = Counter()
        self.reservation_peak = Counter()
        self.aggregate = defaultdict(deque)
        self.future = []
        self.serial = 0
        self.ready = []
        self.native_events=[]
        self.memory_groups = Counter()
        self.accepted = self.completed = 0
        self.aggregate_bytes = Counter()
        self.aggregate_peak = Counter()
        self.aggregate_busy_cycles = Counter()
        self.reservation_stalls = self.queue_stalls = 0
        self.native_first_ps = self.native_last_ps = None
        self.cdc_wait_ps = self.aggregation_wait_ps = 0
        self.channel_atoms = Counter()
        self.last_ps = -1

    def address(self, req, offset):
        word = req.word_address*32 + req.bank + offset//32
        return self.channels[req.memory]*32 + word%32, 2*(word//32) + (offset%32)//16

    def submit(self, req, now):
        if now % self.period_ps:
            return False
        if (req.id in self.groups or req.size_bytes % 32 or req.memory not in self.channels
                or req.size_bytes > self.spec.memory_request_bytes):
            raise ValueError('Invalid/duplicate RWDL descriptor')
        if self.memory_groups[req.memory] >= self.slots[req.memory]:
            return False
        if (req.word_address < 0 or not 0 <= req.bank < 32 or req.size_bytes <= 0
                or req.word_address*32+req.bank+req.size_bytes//32 > (1 << 19)*32):
            raise ValueError('RWDL descriptor exceeds physical array capacity')
        cursors = {c: ((c-req.bank)%32)*32 for c in range(32)}
        self.groups[req.id] = dict(request=req, cursors=cursors, completed=0,raw_completed=0)
        for c, offset in cursors.items():
            if offset < req.size_bytes:
                self.queues[self.channels[req.memory]*32+c].append(req.id)
        self.memory_groups[req.memory] += 1
        self.accepted += 1
        return True

    def advance(self, now):
        if now < self.last_ps:
            raise ValueError('Nonmonotonic RWDL adapter time')
        self.last_ps = now
        for ticket, cycle in self.backend.advance(now):
            key, offset, channel = self.tickets.pop(ticket)
            at = cycle*self.period_ps
            row=self.groups[key]
            row['raw_completed']+=1
            # The native callback is the end of one RWDL/HB beat. Preserve the
            # actual array digital readiness and beat-tail clocks, even if polled later.
            if row['raw_completed']==1:
                self.native_events.append(dict(kind='array_first_ready',request=key,
                    time_ps=at-self.period_ps,beat_tail_ps=at,location=self.native_ready_location))
            if row['raw_completed']*16==row['request'].size_bytes:
                self.native_events.append(dict(kind='array_last_ready',request=key,
                    time_ps=at-self.period_ps,beat_tail_ps=at,location=self.native_ready_location))
            self.native_first_ps = at if self.native_first_ps is None else self.native_first_ps
            self.native_last_ps = at
            sample = ((at+self.spec.noc_period_ps-1)//self.spec.noc_period_ps
                      + self.cdc_cycles)*self.spec.noc_period_ps
            self.cdc_wait_ps += sample-at
            self.serial += 1
            heapq.heappush(self.future,(sample,self.serial,key,offset,channel,at))
        result = []
        if now % self.spec.noc_period_ps == 0:
            while self.future and self.future[0][0] <= now:
                sample, _, key, offset, channel, at = heapq.heappop(self.future)
                memory = self.groups[key]['request'].memory
                self.aggregate[memory].append((key,offset,channel,sample,at))
                self.aggregate_peak[memory] = max(self.aggregate_peak[memory],len(self.aggregate[memory])*16)
            for memory, queue in self.aggregate.items():
                count = min(len(queue),self.aggregation_bytes_per_cycle//16)
                if count: self.aggregate_busy_cycles[memory] += 1
                for _ in range(count):
                    key, offset, channel, sample, at = queue.popleft()
                    self.reserved[channel] -= 1
                    self.aggregate_bytes[memory] += 16
                    self.aggregation_wait_ps += now-sample
                    if self.streaming:self.ready.append((key,offset,16))
                    row = self.groups[key]
                    row['completed'] += 1
                    if row['completed']*16 == row['request'].size_bytes:
                        result.append(key)
                        self.memory_groups[memory] -= 1
                        self.completed += 1
                        del self.groups[key]
        if now % self.period_ps == 0:
            # One shared 32-way dispatcher: at most one atom/channel/CK.
            # Independent channel cursors avoid an artificial cross-channel HOL.
            for channel, queue in self.queues.items():
                if not queue:
                    continue
                if self.reserved[channel] >= self.reservations_per_channel:
                    self.reservation_stalls += 1
                    continue
                index=self.round_robin[channel]%min(self.descriptor_window,len(queue))
                key = queue[index]
                row = self.groups[key]
                req = row['request']
                offset = row['cursors'][channel%32]
                mapped, address = self.address(req,offset)
                if mapped != channel:
                    raise RuntimeError('RWDL channel mapping changed')
                ticket = self.backend.submit(channel,address)
                if ticket is None:
                    self.queue_stalls += 1
                    continue
                self.tickets[ticket] = key,offset,channel
                self.reserved[channel] += 1
                self.reservation_peak[channel] = max(self.reservation_peak[channel],self.reserved[channel])
                self.channel_atoms[channel] += 1
                self.round_robin[channel]=(index+1)%self.descriptor_window
                offset += 16 if offset % 32 == 0 else 1008
                row['cursors'][channel%32] = offset
                if offset >= req.size_bytes:
                    queue.remove(key)
        return result

    def take_ready(self):
        result, self.ready = self.ready, []
        return result

    def take_native_events(self):
        result,self.native_events=self.native_events,[]
        return result

    def resources(self):
        value=dict(arrays_per_memory=32, capacity_bytes_per_array=16*1024**2,
            rw_dl_and_hb_same_lanes=True, data_lanes_per_array=128, data_lanes_per_memory=4096,
            interface_period_ps=3760, interface_peak_GBps_per_memory=32*16*1000/3760,
            command_read_entries_per_array=1 if self.profile is None else self.profile.controller.read_entries,
            command_read_entries_per_memory=32*(1 if self.profile is None else self.profile.controller.read_entries),
            command_write_entries_per_array=1, writes_used=False,
            active_entries_per_array=1, refresh_priority_entries_per_array=1,
            controller_command_issues_per_array_cycle=1, controller_instances_per_memory=32,
            dispatcher_atoms_per_memory_cycle=32,
            reserved_atoms_per_array=self.reservations_per_channel,
            shared_return_reservation_bytes_per_memory=32*self.reservations_per_channel*16,
            return_reservation_lifetime='before native read acceptance through CDC and aggregate drain',
            cdc_cycles=self.cdc_cycles, cdc_policy='ceil native tail to NoC edge, then two NoC cycles',
            native_ready_location=self.native_ready_location,stream_origin=self.stream_origin,
            transport_path=['array digital ready','one RWDL/HB beat','reserved CDC',
                            'shared aggregation','MC staging','NoC/local DMA','SRAM write'],
            array_to_center_wire_length_um=None,array_to_center_wire_cost_calibrated=False,
            aggregation_bits=self.aggregation_bytes_per_cycle*8,
            aggregation_period_ps=self.spec.noc_period_ps,
            descriptor_return_bytes_per_memory=max(self.slots.values())*self.spec.memory_request_bytes,
            shared_mc_slots_per_memory=max(self.slots.values()),
            array_command_control_bits=None, controller_area_um2=None, energy_j=None)
        if self.profile is not None:
            from dataclasses import asdict
            c=self.profile.controller
            value.update(profile=asdict(self.profile),descriptor_candidate_window=c.descriptor_window,
                expansion_policy='per-domain round-robin among first finite descriptor window; native FRFCFS among visible atoms',
                command_entry_bare_min_bits=24,
                command_queue_bare_min_bits_per_memory=32*c.read_entries*24,
                command_queue_extra_entries_per_memory=32*(c.read_entries-1),
                dispatcher_round_robin_bits_per_memory=32*(c.descriptor_window-1).bit_length(),
                bare_min_bits_scope='20-bit array column address + 3-bit reserved return slot + valid; timestamp/control/comparator excluded',
                controller_selection_area_um2=None,refresh_trigger_phase=c.refresh_phase)
        return value

    def record(self):
        value = self.backend.record()
        value.update(boundary=self.boundary,streaming=self.streaming,atomic_bytes=16,
            accepted=self.backend.accepted,completed=self.backend.completed,
            grouped_descriptors_accepted=self.accepted,grouped_descriptors_completed=self.completed,
            pending=len(self.groups)+len(self.tickets)+len(self.future)+sum(map(len,self.aggregate.values())),
            resources=self.resources(),channel_atoms=dict(self.channel_atoms),
            reservation_peak_atoms=dict(self.reservation_peak),reservations_live=sum(self.reserved.values()),
            aggregation_peak_bytes=dict(self.aggregate_peak),aggregation_bytes=dict(self.aggregate_bytes),
            aggregation_busy_cycles=dict(self.aggregate_busy_cycles),
            reservation_stall_attempts=self.reservation_stalls,queue_stall_attempts=self.queue_stalls,
            native_first_tail_ps=self.native_first_ps,native_last_tail_ps=self.native_last_ps,
            cdc_wait_atom_ps=self.cdc_wait_ps,aggregation_wait_atom_ps=self.aggregation_wait_ps)
        return value

    def close(self):
        self.backend.close()
