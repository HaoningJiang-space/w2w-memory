"""Thin boundary adapter to the bundled optimized native BookSim.

SystemExecution owns time and transactions. The native process owns compute
routers, arbitration and credits. Local copies and home-HB segments are finite
serial channels; a memory node is never a native router. Receive storage is
reserved at admission per traffic class, preventing request/response protocol
cycles with the native one-VC network. Classes share physical link bandwidth.
"""
from collections import Counter,deque
from functools import partial
import heapq
from math import ceil
import os
from pathlib import Path
import subprocess
import sys

from w2w.system.local_dma import LocalDma
from w2w.system.receive_write import ReceiveWritePort

PIN = '0c56c24b4bf602b8b2c036681f526971305dde99'


def factory(*, binary, directory, source=None, ideal_return=False, debug_flits=False,
            local_dma='legacy',cell_sideband_bits=0):
    return partial(BookSimNetwork, source=source, binary=binary, directory=directory,
                   ideal_return=ideal_return, debug_flits=debug_flits,local_dma=local_dma,
                   cell_sideband_bits=cell_sideband_bits)


def _config(builder, directory):
    from .native_booksim.online_booksim import prepare_online_config
    root = directory / 'rapidchiplet/booksim2/src'
    for name in ('rc_configs', 'rc_topologies', 'rc_stats', 'rc_xy_info'):
        (root / name).mkdir(parents=True, exist_ok=True)
    nodes = {key: n for n, key in enumerate(builder.tiles)}
    rows = []
    for key, n in nodes.items():
        row = f'router {n} node {n} 1'
        for link in builder.spec.links:
            if link.src == key and link.dst in nodes:
                if link.credit_cycles != link.pipeline_cycles:
                    raise ValueError('Native channel uses the same latency for flits and credits')
                row += f' router {nodes[link.dst]} {link.pipeline_cycles}'
        rows.append(row)
    (root / 'rc_topologies/network.anynet').write_text('\n'.join(rows)+'\n')
    spec = builder.spec
    inputs = dict(chiplets={'tile': dict(router_latency=spec.router_cycles)},
        placement={'chiplets': [{'name': 'tile'} for _ in nodes]},
        routing_table={'type': 'default'},
        booksim_config=dict(mode='trace', trace_file='none', ignore_cycles=0,
            repetitions=1, sim_count=1, trace_time_out=120, time_limit=120,
            precision=.001, saturation_factor=2, traffic='uniform', packet_size=1,
            num_vcs=1, vc_buf_size=spec.input_buffer_flits,
            modular_routing_function='simple_cycle_breaking_set',
            modular_selection_function='adaptive', sample_period=100000,
            warmup_periods=0, wait_for_tail_credit=0, injection_rate_uses_flits=1,
            deadlock_warn_timeout=200000))
    return nodes, prepare_online_config(inputs, directory)


class BookSimNetwork:
    def __init__(self, builder, events, *, source, binary, directory,
                 ideal_return=False, debug_flits=False,local_dma='legacy',cell_sideband_bits=0):
        from .native_booksim.support import digest
        directory = Path(directory).resolve()
        if source is None:
            from .native_booksim.boundary_booksim import BoundaryBookSim
            from .native_booksim import __file__ as package_file
            self.runtime_source = dict(kind='bundled_w2w', files={
                p.name: digest(p) for p in sorted(Path(package_file).parent.glob('*.py'))})
        else:
            # Explicit compatibility path for replaying archived runs. New runs
            # use the bundled implementation, with no sibling checkout needed.
            source = Path(source).resolve()
            revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
            if revision != PIN:
                raise ValueError(f'Use the registered wafer_simulator revision {PIN}')
            sys.path.insert(0, str(source/'src'))
            sys.path.insert(0, str(source/'third_party/nw-design-for-wsi'))
            from wafer_sim.adapters.boundary_booksim import BoundaryBookSim
            self.runtime_source = dict(kind='legacy_external', commit=revision)
        directory.mkdir(parents=True, exist_ok=False)
        self.builder, self.spec, self.events = builder, builder.spec, events
        if local_dma not in ('legacy','payload_beats'):
            raise ValueError('Unknown local DMA contract')
        self.local_dma=local_dma
        self.nodes, config = _config(builder, directory)
        self.node_names = {n: name for name, n in self.nodes.items()}
        self.client = BoundaryBookSim(binary, config, directory, flit_bytes=self.spec.flit_bytes)
        if not debug_flits:
            self.client.logs[2].close()
            self.client.logs[2] = open(os.devnull, 'w')
        self.client.configure(rx_slots=self.spec.input_buffer_flits, bounded=True, streaming=True)
        self.ideal_return, self.debug_flits = ideal_return, debug_flits
        self.pending, self.native_ids = {}, {}
        self.next_id = 0
        self.source_occupied, self.rx_reserved = Counter(), Counter()
        self.rx_peak, self.source_peak = Counter(), Counter()
        self.dma = LocalDma(self.spec)
        self.write_port = ReceiveWritePort(self.spec.rx_write_bytes_per_cycle, self.spec.noc_period_ps)
        self.future, self.serial = [], 0
        self.link_flits, self.wire_bytes = Counter(), Counter()
        self.accepted_bytes, self.delivered_bytes = Counter(), Counter()
        self.link_slots = set()
        self.rejections = self.accepted = self.delivered = 0
        self.native_idle = True
        self.final = None
        self.injection_flits_by_source=Counter()
        self.admission_rejections=Counter()
        if cell_sideband_bits not in (0,64):raise ValueError('Supported cell sideband is legacy unspecified or 64 bits')
        self.cell_sideband_bits=cell_sideband_bits
        self.cell_tags=deque(range(1 << 16)) if self.cell_sideband_bits else None
        self.cell_tag_peak=0

    def log(self, now, kind, **values):
        self.events.append(dict(time_ps=now, kind=kind, **values))

    @property
    def rx_write_bytes(self):
        """Compatibility view; the receive port is the sole state owner."""
        return self.write_port.bytes

    @property
    def rx_write_cycles(self):
        return self.write_port.cycles

    def _future(self, at, kind, key, item=None):
        self.serial += 1
        heapq.heappush(self.future, (at, self.serial, kind, key, item))

    def try_send(self, packet, now, *, streaming=False):
        if now != self.client.now*self.spec.noc_period_ps:
            raise ValueError('Native and system clocks differ at submission')
        if packet.id in self.pending:
            raise ValueError('Duplicate live packet')
        if not 0 <= packet.payload_bytes <= self.spec.packet_payload_bytes:
            raise ValueError('Packet exceeds NI descriptor capacity')
        if packet.route != self.builder.route(packet.src, packet.dst):
            raise ValueError('Packet contains an illegal physical route')
        local_payload=self.local_dma=='payload_beats' and not packet.route
        count = max(1,ceil((packet.payload_bytes+(0 if local_payload else self.spec.header_bytes))/self.spec.flit_bytes))
        rx = packet.dst, packet.traffic_class
        if self.cell_tags is not None and not self.cell_tags:
            self.admission_rejections['cell_tag_pool']+=1
            self.rejections+=1
            return False
        if (self.source_occupied[packet.src]+count > self.spec.injection_flits
                or self.rx_reserved[rx] >= self.spec.ejection_packets):
            if self.source_occupied[packet.src]+count > self.spec.injection_flits:
                self.admission_rejections['source_ni/'+packet.src]+=1
            if self.rx_reserved[rx] >= self.spec.ejection_packets:
                self.admission_rejections['destination_slots/'+packet.dst]+=1
            self.rejections += 1
            return False
        self.source_occupied[packet.src] += count
        self.source_peak[packet.src] = max(self.source_peak[packet.src], self.source_occupied[packet.src])
        self.rx_reserved[rx] += 1
        self.rx_peak[rx] = max(self.rx_peak[rx], self.rx_reserved[rx])
        self.pending[packet.id] = dict(packet=packet, count=count, committed=0, ready=False,
                                      streaming=streaming, supplied=0, payload_prefix=0,
                                      local_payload=local_payload,local_copied=0,local_released=0,
                                      rx_cycles=0,rx_bytes=0,rx_wait_ps=0)
        if self.cell_tags is not None:
            self.pending[packet.id]['cell_tag']=self.cell_tags.popleft()
            self.cell_tag_peak=max(self.cell_tag_peak,len(self.pending))
        self.accepted += 1
        self.accepted_bytes[packet.traffic_class] += packet.payload_bytes
        self.log(now, 'packet_accept', packet=packet.id, src=packet.src, dst=packet.dst,
                 traffic_class=packet.traffic_class, payload_bytes=packet.payload_bytes, flits=count)
        bypass = self.ideal_return and packet.id.endswith('/resp')
        if packet.src in self.nodes and packet.dst in self.nodes and packet.src != packet.dst and not bypass:
            identity = self.next_id
            self.next_id += 1
            self.native_ids[identity] = packet.id
            # Reuse persistent IPC and boundary commands, with adapter-owned IDs.
            # Avoid retaining a second full flit archive in OnlineBookSim.messages.
            self.client._request(dict(command='submit', id=identity, cycle=self.client.now,
                source=self.nodes[packet.src], destination=self.nodes[packet.dst], flits=count))
            self.pending[packet.id]['native_id'] = identity
            if not streaming:
                self.client._request(dict(command='supply', id=identity, cycle=self.client.now, flits=count))
            self.native_idle = False
        else:
            hb = [self.builder.links[k] for k in packet.route if self.builder.links[k].kind == 'HB']
            if hb and (len(hb) != 1 or len(packet.route) != 1):
                raise ValueError('Home HB must terminate at its owning controller')
            if local_payload:
                row=self.pending[packet.id]
                row['local_beats']=max(1,ceil(packet.payload_bytes/self.spec.rx_write_bytes_per_cycle))
                if not streaming:self._supply_local_payload(packet.id,packet.payload_bytes,now)
                return True
            if streaming:
                if hb:
                    raise ValueError('Streaming HB requires an explicit native-domain transport contract')
                # Same finite NI and write port as remote response; scheduled by supply_prefix.
                return True
            if hb:
                link = hb[0]
                beats = ceil((packet.payload_bytes+self.spec.header_bytes)*8/link.width_bits)
                first = self.dma.reserve(link.id, now, beats, link.period_ps)
                at = first+(beats-1+link.pipeline_cycles)*link.period_ps
                for index in range(beats):
                    self._link_send(packet, link, index, first+index*link.period_ps)
            else:
                # Local DMA and ideal return still consume the receive write port.
                at = now+self.spec.noc_period_ps
            self._future(at, 'local', packet.id)
        return True

    def supply_prefix(self, key, prefix_bytes, now):
        """Incremental contiguous payload; flit/header packing stays unchanged."""
        row = self.pending[key]
        packet = row['packet']
        if (not row['streaming'] or now != self.client.now*self.spec.noc_period_ps
                or not row['payload_prefix'] <= prefix_bytes <= packet.payload_bytes):
            raise ValueError('Invalid streaming prefix or clock')
        row['payload_prefix'] = prefix_bytes
        if row['local_payload']:
            return self._supply_local_payload(key,prefix_bytes,now)
        eligible = ((prefix_bytes+self.spec.header_bytes)//self.spec.flit_bytes
                    if prefix_bytes < packet.payload_bytes else row['count'])
        count = eligible-row['supplied']
        if count:
            if 'native_id' in row:
                self.client._request(dict(command='supply',id=row['native_id'],
                                          cycle=self.client.now,flits=count))
                self.native_idle = False
            else:
                for at,size in self.dma.legacy_fragments(packet,row['supplied'],eligible,now):
                    self._future(at,'stream_local',key,size)
            if row['supplied'] == 0:
                self._supply_log(now,'first',packet,prefix_bytes)
            row['supplied'] = eligible
            if eligible == row['count']:
                self._supply_log(now,'last',packet,prefix_bytes)
        return row['supplied'] == row['count']

    def _supply_log(self,now,which,packet,prefix):
        name='response' if packet.traffic_class=='response' else 'payload'
        self.log(now,name+'_'+which+'_supply',packet=packet.id,payload_prefix_bytes=prefix)

    def _supply_local_payload(self,key,prefix,now):
        row=self.pending[key];packet=row['packet']
        width=self.spec.rx_write_bytes_per_cycle
        eligible=prefix//width if prefix<packet.payload_bytes else row['local_beats']
        for at,size in self.dma.payload_beats(packet,row['supplied'],eligible,now):
            self._future(at,'local_payload',key,size)
        if eligible>row['supplied']:
            if row['streaming'] and row['supplied']==0:self._supply_log(now,'first',packet,prefix)
            row['supplied']=eligible
            if row['streaming'] and eligible==row['local_beats']:self._supply_log(now,'last',packet,prefix)
        return row['supplied']==row['local_beats']

    def packet_metrics(self,key):
        row=self.pending[key]
        return {k:row[k] for k in ('rx_cycles','rx_bytes','rx_wait_ps')}

    def _link_send(self, packet, link, ordinal, at):
        slot = link.resource_id, at
        if slot in self.link_slots:
            raise RuntimeError('Physical channel overbooked')
        self.link_slots.add(slot)
        self.link_flits[link.id] += 1
        self.wire_bytes[packet.traffic_class] += link.width_bits//8
        if self.debug_flits:
            self.log(at, 'link_send', packet=packet.id, link=link.id,
                     resource=link.resource_id, flit=ordinal)

    def _write(self, packet, size, at, fid=None):
        # All activation and response writes contend for one declared tile port.
        # Header-only requests are copied into pre-reserved finite MC NI storage.
        to_sram = packet.traffic_class == 'activation' or packet.id.endswith('/resp')
        if packet.dst in self.nodes and size and to_sram:
            at,cycles,wait_ps = self.write_port.reserve(packet.dst,packet.traffic_class,size,at)
            row=self.pending[packet.id]
            row['rx_cycles']+=cycles;row['rx_bytes']+=size;row['rx_wait_ps']+=wait_ps
        self._future(at, 'commit', packet.id, fid)

    def _advance(self, now):
        target = now//self.spec.noc_period_ps
        while self.client.now < target:
            reply = self.client._request(dict(command='advance', until=target))
            if not self.client.now < reply['cycle'] <= target:
                raise RuntimeError('Native advance did not respect the system boundary')
            self.client.now = reply['cycle']
            self.native_idle = reply['idle']
            for event in reply.get('progress', []):
                key = self.native_ids[event['id']]
                row = self.pending[key]
                packet = row['packet']
                if event['event'] == 'inject':
                    self.source_occupied[packet.src] -= 1
                    self.injection_flits_by_source[packet.src]+=1
                elif event['event'] == 'receive':
                    record = event['record']
                    for hop in record['link_arrivals']:
                        src, dst = self.node_names[hop['source']], self.node_names[hop['destination']]
                        link = self.builder.links[self.builder.edges[src, dst]]
                        self._link_send(packet, link, event['ordinal'],
                                        (hop['cycle']-link.pipeline_cycles)*self.spec.noc_period_ps)
                    first = event['ordinal']*self.spec.flit_bytes
                    size = max(0, min(first+self.spec.flit_bytes,
                                     packet.payload_bytes+self.spec.header_bytes)-max(first, self.spec.header_bytes))
                    self._write(packet, size, event['cycle']*self.spec.noc_period_ps, event['flit'])
                else:
                    raise RuntimeError('Unknown native boundary event')
            for event in reply['completed']:
                row = self.pending[self.native_ids[event['id']]]
                if len(event['flits']) != row['count']:
                    raise RuntimeError('Native message lost flits')

    def arrive(self, now):
        if now % self.spec.noc_period_ps:
            return
        self._advance(now)
        while self.future and self.future[0][0] <= now:
            at, _, kind, key, fid = heapq.heappop(self.future)
            row = self.pending[key]
            packet = row['packet']
            if kind == 'local':
                self.source_occupied[packet.src] -= row['count']
                self._write(packet, packet.payload_bytes, at)
            elif kind == 'stream_local':
                self.source_occupied[packet.src] -= 1
                self._write(packet, fid, at, 'local-stream')
            elif kind=='local_payload':
                row['local_copied']+=fid
                released=(row['count'] if row['local_copied']==packet.payload_bytes
                          else row['local_copied']//self.spec.flit_bytes)
                self.source_occupied[packet.src]-=released-row['local_released']
                row['local_released']=released
                self._write(packet,fid,at,'payload-beat')
            elif kind == 'commit':
                if fid == 'payload-beat':
                    row['committed']+=1
                    row['ready']=row['committed']==row['local_beats']
                    continue
                elif fid == 'local-stream':
                    row['committed'] += 1
                elif fid is not None:
                    self.client.commit(fid)
                    self.native_idle = False  # returned credits still require native drain
                    row['committed'] += 1
                else:
                    row['committed'] = row['count']
                row['ready'] = row['committed'] == row['count']

    def deliver(self, now, accept):
        for key, row in list(self.pending.items()):
            packet = row['packet']
            if row['ready'] and accept(packet):
                self.rx_reserved[packet.dst, packet.traffic_class] -= 1
                self.delivered_bytes[packet.traffic_class] += packet.payload_bytes
                self.delivered += 1
                self.log(now, 'packet_deliver', packet=key, src=packet.src, dst=packet.dst,
                         traffic_class=packet.traffic_class, payload_bytes=packet.payload_bytes)
                del self.pending[key]
                if self.cell_tags is not None:self.cell_tags.append(row['cell_tag'])

    def step(self, now):
        pass  # next kernel boundary advances the native component

    def drained(self):
        return not self.pending and not self.future and self.native_idle

    def record(self):
        return dict(kind='native_boundary_booksim', source_commit=PIN,
                    runtime_source=self.runtime_source,
                    identity=self.client.identity, ideal_return=self.ideal_return,
                    packetization='header+payload; native single-flit packets',
                    local_dma_contract=self.local_dma,
                    receive_reservation='ideal instantaneous global booking; control protocol not simulated',
                    cell_format=dict(data_bits=self.spec.flit_bytes*8,sideband_bits=self.cell_sideband_bits,
                        fields={'source':6,'destination':6,'traffic_class':2,'message_tag':16,
                                'ordinal':8,'valid_payload_bytes':10,'first_last':2,'reserved':14},
                        message_envelope_bytes=self.spec.header_bytes,tag_slots=1 << 16,
                        live_tag_peak=self.cell_tag_peak,
                        scope='declared sideband reference, simulation IDs/path histories are not wire fields'),
                    routing='native simple_cycle_breaking_set/adaptive',
                    event_level='flit' if self.debug_flits else 'transaction',
                    accepted_packets=self.accepted, delivered_packets=self.delivered,
                    accepted_bytes=dict(self.accepted_bytes), delivered_bytes=dict(self.delivered_bytes),
                    link_flits=dict(self.link_flits), wire_bytes_by_class=dict(self.wire_bytes),
                    source_peak_flits=dict(self.source_peak),
                    source_injected_flits=dict(self.injection_flits_by_source),
                    rx_write_bytes=dict(self.write_port.bytes),rx_write_cycles=dict(self.write_port.cycles),
                    rx_write_cycles_by_class=dict(self.write_port.cycles_by_class),
                    rx_job_wait_sum_ps=dict(self.write_port.wait_ps),
                    admission_rejection_attempts=dict(self.admission_rejections),
                    rx_reserved_peak={str(k): v for k, v in self.rx_peak.items()},
                    ni_rx_capacity_bytes_per_node=3*self.spec.ejection_packets*(self.spec.packet_payload_bytes+self.spec.header_bytes),
                    ni_tx_capacity_bytes_per_node=self.spec.injection_flits*self.spec.flit_bytes,
                    rejections=self.rejections, drained=self.drained(), final=self.final)

    def close(self):
        if not self.drained():
            raise RuntimeError('Cannot close a live native network')
        self.final = self.client.close()['final']
        pressure=self.final.get('source_pressure')
        if pressure:
            self.final['source_pressure_nodes']={k:{self.node_names[n]:value for n,value in enumerate(v) if value}
                for k,v in pressure.items() if k.endswith('_cycles')}
            raw=dict(pressure['unsupplied_by_message'])
            behind=dict(pressure['ready_behind_by_message'])
            self.final['source_head_wait_by_packet']={self.native_ids[int(k)]:dict(
                unsupplied_cycles=v,ready_behind_cycles=behind.get(k,0)) for k,v in raw.items()}

    def abort(self):
        self.client.abort()
