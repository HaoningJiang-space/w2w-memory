"""One integer-ps clock for data delivery, SRAM, compute, network and DRAM.

Blocking task working sets are reserved before input DMA; users must provide
explicitly tiled tasks when they exceed SRAM. Source output storage is freed
when copied into a bounded NI, not by a free remote completion acknowledgement.
"""
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from math import gcd
import json

from w2w.domain.protocol import Packet
from w2w.mapping.address_map import words_for_task
from w2w.system.builder import SystemBuilder


class SystemExecution:
    def __init__(self, spec, graph, native=None, *, network_factory=None,
                 activation_sram_read_bytes_per_cycle=None):
        self.spec, self.graph = spec, graph
        self.builder = SystemBuilder(spec).validate_graph(graph)
        self.events = []
        if native is None or network_factory is None:
            raise ValueError('Architecture V3 requires explicit native memory and fabric backends')
        self.network = network_factory(self.builder, self.events)
        self.native = native
        if self.native.boundary not in ('memory_word_ready_before_explicit_HB',
                                        'controller_payload_ready_after_native_bus'):
            raise ValueError('Unknown DRAM callback boundary')
        self.native_at_controller = self.native.boundary.startswith('controller_')
        self.streaming = getattr(self.native, 'streaming', False)
        self.stream_origin=getattr(self.native,'stream_origin',
                                   'home_controller' if self.native_at_controller else 'array')
        if self.streaming and (self.stream_origin!='home_controller' or not hasattr(self.network,'supply_prefix')):
            raise ValueError('Streaming return must declare its transport-complete home-controller origin')
        if activation_sram_read_bytes_per_cycle is not None and (
                type(activation_sram_read_bytes_per_cycle) is not int
                or activation_sram_read_bytes_per_cycle<1 or not hasattr(self.network,'supply_prefix')):
            raise ValueError('Explicit SRAM read port requires positive width and finite prefix network')
        self.activation_sram_read_bytes_per_cycle=activation_sram_read_bytes_per_cycle
        self.sram_read_bytes,self.sram_read_cycles=Counter(),Counter()
        self.tasks = {t.id: t for t in graph.tasks}
        self.predecessors = {t.id: {e.producer for e in (*graph.control, *graph.data) if e.consumer == t.id}
                             for t in graph.tasks}
        self.task_order = sorted(self.tasks)
        self.unallocated = set(self.tasks)
        self.ready_tasks = set()
        self.reading = set()
        self.state = {t.id: dict(allocated=False, start_ps=None, finish_ps=None,
                                read_bytes=0, issued_all=False, next_read=None,
                                iterator=iter(words_for_task(t, graph, self.builder))) for t in graph.tasks}
        self.edges = {e.id: dict(edge=e, sent=0, delivered=0) for e in graph.data}
        self.requests = {}
        self.packet_info = {}
        self.sram = Counter()
        self.sram_peak = Counter()
        self.engine = {}
        self.busy_ps = Counter()
        self.engine_context_ps=Counter()
        self.outstanding = Counter()
        self.outstanding_peak = Counter()
        self.mc_slots = Counter()
        self.mc_peak = Counter()
        self.mc_pool_slots=Counter()
        self.mc_pool_peak=Counter()
        self.now = 0

    def log(self, kind, **data):
        self.events.append(dict(time_ps=self.now, kind=kind, **data))

    def _sram(self, tile, amount, task):
        self.sram[tile] += amount
        if not 0 <= self.sram[tile] <= self.builder.tiles[tile].sram_bytes:
            raise RuntimeError('SRAM reservation conservation failure')
        self.sram_peak[tile] = max(self.sram_peak[tile], self.sram[tile])
        self.log('sram_change', tile=tile, task=task, bytes=amount)

    def _send(self, key, src, dst, cls, size, kind, item, *, streaming=False):
        packet = Packet(key, src, dst, cls, size, self.builder.route(src, dst))
        accepted=(self.network.try_send(packet,self.now,streaming=True) if streaming
                  else self.network.try_send(packet,self.now))
        if not accepted:
            return False
        self.packet_info[key] = kind, item, size
        return True

    def _receive(self, packet):
        kind, key, size = self.packet_info[packet.id]
        if kind == 'data':
            self.edges[key]['delivered'] += size
            self.log('data_deliver', edge=key, bytes=size)
        else:
            row = self.requests[key]
            req = row['request']
            if kind == 'request':
                memory = self.builder.memories[req.memory]
                pool=getattr(memory,'mc_pool_id',req.memory)
                if self.mc_pool_slots[pool] >= memory.transaction_slots:
                    return False
                self.mc_slots[req.memory] += 1
                self.mc_pool_slots[pool]+=1
                self.mc_pool_peak[pool]=max(self.mc_pool_peak[pool],self.mc_pool_slots[pool])
                self.mc_peak[req.memory] = max(self.mc_peak[req.memory], self.mc_slots[req.memory])
                row['stage'] = 'native_wait' if self.native_at_controller else 'command_send'
                self.log('mc_accept', request=key, memory=req.memory)
            elif kind == 'command':
                row['stage'] = 'native_wait'
            elif kind == 'hb_return':
                row['stage'] = 'response_send'
            elif kind == 'response':
                row['stage'] = 'delivered'
                self.state[req.task]['read_bytes'] += req.size_bytes
                stream=getattr(self.tasks[req.task],'stream',None)
                if stream is not None:
                    state=self.state[req.task]
                    name='stream_scale_delivered' if req.object_offset>=stream.weight_data_bytes else 'stream_weight_delivered'
                    state[name]=state.get(name,0)+req.size_bytes
                self.outstanding[req.requester] -= 1
                self.log('read_deliver', request=key, task=req.task, bytes=req.size_bytes,
                         memory=req.memory, bank=req.bank, word_address=req.word_address,
                         receive_service=(self.network.packet_metrics(packet.id)
                            if hasattr(self.network,'packet_metrics') else None))
                if stream is not None:
                    self.log('stream_operand_ready',task=req.task,request=key,object=req.object_id,
                        object_offset=req.object_offset,bytes=req.size_bytes)
                del self.requests[key]
            else:
                raise RuntimeError('Unknown transaction packet')
        del self.packet_info[packet.id]
        return True

    def _compute_completions(self):
        for tile, key in list(self.engine.items()):
            state = self.state[key]
            if state['finish_ps'] is None or state['finish_ps'] > self.now:
                continue
            task = self.tasks[key]
            del self.engine[tile]
            output = sum(e.size_bytes for e in self.graph.data if e.producer == key)
            self._sram(tile, -(self.builder.footprint[key]-output), key)
            state['done'] = True
            self.engine_context_ps[tile]+=self.now-state['start_ps']
            self.log('task_finish', task=key, tile=tile)

    def _allocate(self):
        for key in sorted(self.unallocated):
            state, task = self.state[key], self.tasks[key]
            if state['allocated'] or self.now < task.release_ps:
                continue
            predecessors = self.predecessors[key]
            if any(not self.state[p].get('done') for p in predecessors):
                continue
            size = self.builder.footprint[key]
            if self.sram[task.tile]+size > self.builder.tiles[task.tile].sram_bytes:
                continue
            self._sram(task.tile, size, key)
            state['allocated'] = True
            self.unallocated.remove(key)
            self.ready_tasks.add(key)
            self.reading.add(key)
            self.log('task_allocate', task=key, tile=task.tile)

    def _data_transfers(self):
        if self.activation_sram_read_bytes_per_cycle is not None:
            return self._ported_data_transfers()
        for key in sorted(self.edges):
            row = self.edges[key]
            edge = row['edge']
            if (not self.state[edge.producer].get('done')
                    or not self.state[edge.consumer]['allocated'] or row['sent'] == edge.size_bytes):
                continue
            src, dst = self.tasks[edge.producer].tile, self.tasks[edge.consumer].tile
            size = min(self.spec.packet_payload_bytes, edge.size_bytes-row['sent'])
            if self._send(f'data/{key}/{row["sent"]}', src, dst, 'activation', size, 'data', key):
                row['sent'] += size
                self._sram(src, -size, edge.producer)
                self.log('data_issue', edge=key, bytes=size)

    def _ported_data_transfers(self):
        used=Counter()
        for key in sorted(self.edges):
            row=self.edges[key];edge=row['edge']
            if (not self.state[edge.producer].get('done')
                    or not self.state[edge.consumer]['allocated'] or row['sent']==edge.size_bytes):
                continue
            src,dst=self.tasks[edge.producer].tile,self.tasks[edge.consumer].tile
            if 'copy' not in row:
                size=min(self.spec.packet_payload_bytes,edge.size_bytes-row['sent'])
                packet=f'data/{key}/{row["sent"]}'
                if not self._send(packet,src,dst,'activation',size,'data',key,streaming=True):
                    continue
                row['copy']=dict(packet=packet,size=size,prefix=0)
            copy=row['copy']
            size=min(copy['size']-copy['prefix'],self.activation_sram_read_bytes_per_cycle-used[src])
            if size<=0:continue
            used[src]+=size;copy['prefix']+=size;row['sent']+=size
            self.sram_read_bytes[src]+=size
            self._sram(src,-size,edge.producer)
            self.log('data_issue',edge=key,bytes=size)
            complete=self.network.supply_prefix(copy['packet'],copy['prefix'],self.now)
            if copy['prefix']==copy['size']:
                if not complete:raise RuntimeError('Source SRAM read completed without full NI supply')
                del row['copy']
        for src in used:self.sram_read_cycles[src]+=1

    def _read_issue(self):
        # Explicit descriptor issue slots; all classes share the finite NI output.
        used = Counter()
        for key in sorted(self.reading):
            task, state = self.tasks[key], self.state[key]
            if (not state['allocated'] or state['issued_all'] or used[task.tile] >= self.spec.read_requests_per_tile_cycle
                    or self.outstanding[task.tile] >= self.spec.outstanding_per_tile):
                continue
            while (used[task.tile] < self.spec.read_requests_per_tile_cycle
                   and self.outstanding[task.tile] < self.spec.outstanding_per_tile):
                if state['next_read'] is None:
                    state['next_read'] = next(state['iterator'], None)
                req = state['next_read']
                if req is None:
                    state['issued_all'] = True
                    self.reading.remove(key)
                    break
                mc = self.builder.memories[req.memory].home_tile
                if not self._send(req.id+'/req', task.tile, mc, 'request', 0, 'request', req.id):
                    break
                self.requests[req.id] = dict(request=req, stage='request_flight')
                state['next_read'] = None
                self.outstanding[task.tile] += 1
                self.outstanding_peak[task.tile] = max(self.outstanding_peak[task.tile], self.outstanding[task.tile])
                used[task.tile] += 1
                self.log('read_issue', request=req.id, task=key, memory=req.memory,
                         bank=req.bank, word_address=req.word_address, bytes=req.size_bytes)

    def _memory_progress(self, network_boundary):
        for key in sorted(self.requests):
            row = self.requests[key]
            req = row['request']
            mc = self.builder.memories[req.memory].home_tile
            stage = row['stage']
            if self.streaming and row.get('native_started'):
                if network_boundary:
                    self._stream_response(key, row, mc)
                continue
            if stage == 'native_wait':
                if self.native.submit(req, self.now):
                    row['stage'] = 'native_pending'
                    if self.streaming:
                        row.update(native_started=True,native_done=False,ready_mask=0,prefix=0,
                                   response_admitted=False,mc_released=False)
                    self.log('native_accept', request=key)
            elif network_boundary and stage == 'command_send':
                if self._send(key+'/cmd', mc, req.memory, 'request', 0, 'command', key):
                    row['stage'] = 'command_flight'
            elif network_boundary and stage == 'hb_send':
                if self._send(key+'/hb', req.memory, mc, 'response', req.size_bytes, 'hb_return', key):
                    row['stage'] = 'hb_flight'
            elif network_boundary and stage == 'response_send':
                if self._send(key+'/resp', mc, req.requester, 'response', req.size_bytes, 'response', key):
                    row['stage'] = 'response_flight'
                    # Data copied into a finite NI. MC transaction/return slot is now reusable.
                    self._release_mc(req)
                    self.log('mc_release', request=key, memory=req.memory)

    def _stream_response(self, key, row, mc):
        req = row['request']
        if not row['prefix'] or row['mc_released']:
            return
        packet_key = key+'/resp'
        if not row['response_admitted']:
            packet = Packet(packet_key,mc,req.requester,'response',req.size_bytes,
                            self.builder.route(mc,req.requester))
            if not self.network.try_send(packet,self.now,streaming=True):
                return
            row['response_admitted'] = True
            row['stage'] = 'response_flight'
            self.packet_info[packet_key] = 'response',key,req.size_bytes
        if self.network.supply_prefix(packet_key,row['prefix'],self.now):
            if not row['native_done']:
                raise RuntimeError('Response supplied before all native words completed')
            # Full NI reservation now owns all bytes; MC slot remains held until this point.
            self._release_mc(req)
            row['mc_released'] = True
            self.log('mc_release',request=key,memory=req.memory)

    def _release_mc(self,req):
        self.mc_slots[req.memory]-=1
        self.mc_pool_slots[getattr(self.builder.memories[req.memory],'mc_pool_id',req.memory)]-=1

    def _native_progress(self):
        complete = self.native.advance(self.now)
        if hasattr(self.native,'take_native_events'):
            self.events.extend(self.native.take_native_events())
        if self.streaming:
            atom = self.native.atomic_bytes
            for key,offset,size in self.native.take_ready():
                row = self.requests[key]
                req = row['request']
                if not row.get('native_started') or size != atom or offset % atom or not 0 <= offset < req.size_bytes:
                    raise RuntimeError('Invalid native byte readiness')
                bit = 1 << (offset//atom)
                if row['ready_mask'] & bit:
                    raise RuntimeError('Repeated native byte readiness')
                if not row['ready_mask']:
                    self.log('native_first_ready',request=key)
                row['ready_mask'] |= bit
                while row['prefix'] < req.size_bytes and row['ready_mask'] & (1 << (row['prefix']//atom)):
                    row['prefix'] += atom
        for key in complete:
            if key not in self.requests:
                raise RuntimeError('Unknown native completion')
            row = self.requests[key]
            if self.streaming:
                if row['native_done'] or row['prefix'] != row['request'].size_bytes:
                    raise RuntimeError('Native descriptor completed without full byte coverage')
                row['native_done'] = True
            else:
                if row['stage'] != 'native_pending':
                    raise RuntimeError('Repeated or unknown native callback')
                row['stage'] = 'response_send' if self.native_at_controller else 'hb_send'
            self.log('native_ready',request=key)

    def _start_compute(self):
        for key in sorted(self.ready_tasks):
            task, state = self.tasks[key], self.state[key]
            tile = self.builder.tiles[task.tile]
            if (not state['allocated'] or state['start_ps'] is not None
                    or task.tile in self.engine or self.now % tile.compute_period_ps):
                continue
            stream=getattr(task,'stream',None)
            if stream is None and state['read_bytes'] != sum(r.size_bytes for r in task.reads):
                continue
            if stream is not None and state.get('stream_scale_delivered',0)!=stream.scale_bytes:
                continue
            if any(row['delivered'] != row['edge'].size_bytes for row in self.edges.values()
                   if row['edge'].consumer == key):
                continue
            state['start_ps'] = self.now
            duration = task.compute_cycles*tile.compute_period_ps
            state['finish_ps'] = self.now+duration if stream is None else None
            self.engine[task.tile] = key
            self.ready_tasks.remove(key)
            if stream is None:self.busy_ps[task.tile] += duration
            self.log('task_start', task=key, tile=task.tile)

    def _stream_compute_progress(self):
        for tile,key in self.engine.items():
            task=self.tasks[key];stream=getattr(task,'stream',None);state=self.state[key]
            period=self.builder.tiles[tile].compute_period_ps
            if stream is None or state['finish_ps'] is not None or self.now%period or state.get('stream_tick')==self.now:
                continue
            state['stream_tick']=self.now
            if not state.get('stream_scale_consumed'):
                state['stream_scale_consumed']=True
                self.busy_ps[tile]+=period
                self.log('stream_compute',task=key,tile=tile,weight_bytes=0,scale_bytes=stream.scale_bytes,macs=0)
                continue
            consumed=state.get('stream_consumed',0)
            reuse=stream.macs//stream.weight_data_bytes
            available=state.get('stream_weight_delivered',0)-consumed
            size=min(available,stream.weight_read_bytes_per_cycle,stream.macs_per_cycle//reuse)
            if size<=0:continue
            state['stream_consumed']=consumed+size;self.busy_ps[tile]+=period
            self.log('stream_compute',task=key,tile=tile,weight_bytes=size,scale_bytes=0,macs=size*reuse)
            if state['stream_consumed']==stream.weight_data_bytes:
                if state['read_bytes']!=sum(r.size_bytes for r in task.reads):raise RuntimeError('GEMM consumed unavailable weights')
                state['finish_ps']=self.now+period

    def _times(self, periods, quantum, max_ps, mode):
        if mode == 'gcd':
            yield from range(0,max_ps+1,quantum)
            return
        if mode != 'boundaries':
            raise ValueError('Unknown time advance mode')
        # Keep the same phases and absolute-time clock semantics. Include local
        # release/completion and scheduled arrivals, rounded to the old ps grid.
        releases = sorted({((t.release_ps+quantum-1)//quantum)*quantum for t in self.graph.tasks})
        now = 0
        while now <= max_ps:
            yield now
            candidates = [(now//period+1)*period for period in set(periods)]
            while releases and releases[0] <= now:
                releases.pop(0)
            if releases: candidates.append(releases[0])
            candidates.extend(self.state[k]['finish_ps'] for k in self.engine.values()
                              if self.state[k]['finish_ps'] is not None and self.state[k]['finish_ps'] > now)
            for component in (self.network,self.native):
                future = getattr(component,'future',None)
                if future and future[0][0] > now:
                    candidates.append(((future[0][0]+quantum-1)//quantum)*quantum)
            now = min(candidates)

    def run(self, max_ps=10_000_000, *, time_advance='gcd'):
        periods = [self.spec.noc_period_ps, self.spec.dram_period_ps,
                   *(t.compute_period_ps for t in self.spec.tiles)]
        quantum = gcd(*periods)
        makespan = None
        iterations = 0
        for self.now in self._times(periods,quantum,max_ps,time_advance):
            iterations += 1
            self.network.arrive(self.now)
            # Packet acceptance happens before new local arbitration, with finite endpoint storage.
            if self.now % self.spec.noc_period_ps == 0:
                self.network.deliver(self.now, self._receive)
            self._native_progress()
            # Resolve local zero-duration control nodes, never bypass data delivery.
            for _ in range(len(self.tasks)+1):
                before = sum(bool(s.get('done')) for s in self.state.values())
                self._compute_completions()
                self._allocate()
                self._start_compute()
                self._stream_compute_progress()
                after = sum(bool(s.get('done')) for s in self.state.values())
                if before == after and not any(self.state[k]['finish_ps'] == self.now for k in self.engine.values()):
                    break
            boundary = self.now % self.spec.noc_period_ps == 0
            if boundary:
                self._data_transfers()
                self._read_issue()
            self._memory_progress(boundary)
            if boundary:
                self.network.step(self.now)
            if all(s.get('done') for s in self.state.values()) and makespan is None:
                makespan = self.now
            if makespan is not None and self.network.drained():
                if (any(self.outstanding.values()) or any(self.sram.values()) or any(self.mc_slots.values())
                        or any(row['stage'] != 'delivered' for row in self.requests.values())
                        or self.native.record()['pending']):
                    raise RuntimeError('System completed with live resources')
                break
        else:
            pending = {k: dict(allocated=s['allocated'], started=s['start_ps'], read_bytes=s['read_bytes'])
                       for k, s in self.state.items() if not s.get('done')}
            raise RuntimeError(f'System stalled or exceeded explicit time limit; no forced releases: {pending}')
        if hasattr(self.network, 'close'):
            self.network.close()
        self.events.sort(key=lambda event: event['time_ps'])
        record = dict(schema='w2w.system-execution.v3' if self.builder.v3 else 'w2w.system-execution.v2',
                      scope='architecture_v3_execution' if self.builder.v3 else 'system_execution_v2_prototype',
                      makespan_ps=makespan, drained_ps=self.now, quantum_ps=quantum,
                      time_advance=time_advance, kernel_iterations=iterations,
                      spec=asdict(self.spec), graph=asdict(self.graph),
                      tasks={k: {v: s[v] for v in ('start_ps', 'finish_ps', 'read_bytes')} for k, s in self.state.items()},
                      sram_peak_bytes=dict(self.sram_peak), compute_busy_ps=dict(self.busy_ps),
                      engine_context_ps=dict(self.engine_context_ps),
                      activation_sram_read_bytes_per_cycle=self.activation_sram_read_bytes_per_cycle,
                      sram_read_bytes=dict(self.sram_read_bytes),sram_read_busy_cycles=dict(self.sram_read_cycles),
                      outstanding_peak=dict(self.outstanding_peak), mc_peak=dict(self.mc_peak),
                      mc_pool_peak=dict(self.mc_pool_peak),
                      network=self.network.record(), native=self.native.record(),
                      physical=self.builder.physical_record(), events=self.events)
        record['input_sha256'] = sha256(json.dumps([record['spec'], record['graph']], sort_keys=True).encode()).hexdigest()
        return record


def execute_system(spec, graph, *, native=None, network_factory=None, max_ps=10_000_000,
                   time_advance='gcd',activation_sram_read_bytes_per_cycle=None):
    execution = SystemExecution(spec, graph, native, network_factory=network_factory,
                                activation_sram_read_bytes_per_cycle=activation_sram_read_bytes_per_cycle)
    try:
        return execution.run(max_ps,time_advance=time_advance)
    except BaseException:
        if hasattr(execution.network, 'abort'):
            execution.network.abort()
        raise
