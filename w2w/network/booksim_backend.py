"""Thin boundary adapter to wafer_simulator's pinned native BookSim.

SystemExecution owns time and transactions. The native process owns compute
routers, arbitration and credits. Local copies and home-HB segments are finite
serial channels; a memory node is never a native router. Receive storage is
reserved at admission per traffic class, preventing request/response protocol
cycles with the native one-VC network. Classes share physical link bandwidth.
"""
from collections import Counter
from functools import partial
import heapq
from math import ceil
import os
from pathlib import Path
import subprocess
import sys

PIN = '0c56c24b4bf602b8b2c036681f526971305dde99'


def factory(*, source, binary, directory, ideal_return=False, debug_flits=False):
    return partial(BookSimNetwork, source=source, binary=binary, directory=directory,
                   ideal_return=ideal_return, debug_flits=debug_flits)


def _config(builder, directory):
    from wafer_sim.adapters.online_booksim import prepare_online_config
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
                 ideal_return=False, debug_flits=False):
        source, directory = Path(source).resolve(), Path(directory).resolve()
        revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
        if revision != PIN:
            raise ValueError(f'Use the registered wafer_simulator revision {PIN}')
        sys.path.insert(0, str(source/'src'))
        sys.path.insert(0, str(source/'third_party/nw-design-for-wsi'))
        from wafer_sim.adapters.boundary_booksim import BoundaryBookSim
        directory.mkdir(parents=True, exist_ok=False)
        self.builder, self.spec, self.events = builder, builder.spec, events
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
        self.local_free, self.write_free = Counter(), Counter()
        self.future, self.serial = [], 0
        self.link_flits, self.wire_bytes = Counter(), Counter()
        self.accepted_bytes, self.delivered_bytes = Counter(), Counter()
        self.link_slots = set()
        self.rejections = self.accepted = self.delivered = 0
        self.native_idle = True
        self.final = None

    def log(self, now, kind, **values):
        self.events.append(dict(time_ps=now, kind=kind, **values))

    def _future(self, at, kind, key, item=None):
        self.serial += 1
        heapq.heappush(self.future, (at, self.serial, kind, key, item))

    def try_send(self, packet, now):
        if now != self.client.now*self.spec.noc_period_ps:
            raise ValueError('Native and system clocks differ at submission')
        if packet.id in self.pending:
            raise ValueError('Duplicate live packet')
        if not 0 <= packet.payload_bytes <= self.spec.packet_payload_bytes:
            raise ValueError('Packet exceeds NI descriptor capacity')
        if packet.route != self.builder.route(packet.src, packet.dst):
            raise ValueError('Packet contains an illegal physical route')
        count = ceil((packet.payload_bytes+self.spec.header_bytes)/self.spec.flit_bytes)
        rx = packet.dst, packet.traffic_class
        if (self.source_occupied[packet.src]+count > self.spec.injection_flits
                or self.rx_reserved[rx] >= self.spec.ejection_packets):
            self.rejections += 1
            return False
        self.source_occupied[packet.src] += count
        self.source_peak[packet.src] = max(self.source_peak[packet.src], self.source_occupied[packet.src])
        self.rx_reserved[rx] += 1
        self.rx_peak[rx] = max(self.rx_peak[rx], self.rx_reserved[rx])
        self.pending[packet.id] = dict(packet=packet, count=count, committed=0, ready=False)
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
            self.client._request(dict(command='supply', id=identity, cycle=self.client.now, flits=count))
            self.native_idle = False
        else:
            hb = [self.builder.links[k] for k in packet.route if self.builder.links[k].kind == 'HB']
            if hb and (len(hb) != 1 or len(packet.route) != 1):
                raise ValueError('Home HB must terminate at its owning controller')
            if hb:
                link = hb[0]
                beats = ceil((packet.payload_bytes+self.spec.header_bytes)*8/link.width_bits)
                first = max(now, self.local_free[link.id])
                self.local_free[link.id] = first+beats*link.period_ps
                at = first+(beats-1+link.pipeline_cycles)*link.period_ps
                for index in range(beats):
                    self._link_send(packet, link, index, first+index*link.period_ps)
            else:
                # Local DMA and ideal return still consume the receive write port.
                at = now+self.spec.noc_period_ps
            self._future(at, 'local', packet.id)
        return True

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
            start = max(at, self.write_free[packet.dst])
            duration = ceil(size/self.spec.rx_write_bytes_per_cycle)*self.spec.noc_period_ps
            at = start+duration
            self.write_free[packet.dst] = at
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
            elif kind == 'commit':
                if fid is not None:
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

    def step(self, now):
        pass  # next kernel boundary advances the native component

    def drained(self):
        return not self.pending and not self.future and self.native_idle

    def record(self):
        return dict(kind='native_boundary_booksim', source_commit=PIN,
                    identity=self.client.identity, ideal_return=self.ideal_return,
                    packetization='header+payload; native single-flit packets',
                    routing='native simple_cycle_breaking_set/adaptive',
                    event_level='flit' if self.debug_flits else 'transaction',
                    accepted_packets=self.accepted, delivered_packets=self.delivered,
                    accepted_bytes=dict(self.accepted_bytes), delivered_bytes=dict(self.delivered_bytes),
                    link_flits=dict(self.link_flits), wire_bytes_by_class=dict(self.wire_bytes),
                    source_peak_flits=dict(self.source_peak),
                    rx_reserved_peak={str(k): v for k, v in self.rx_peak.items()},
                    ni_rx_capacity_bytes_per_node=3*self.spec.ejection_packets*(self.spec.packet_payload_bytes+self.spec.header_bytes),
                    ni_tx_capacity_bytes_per_node=self.spec.injection_flits*self.spec.flit_bytes,
                    rejections=self.rejections, drained=self.drained(), final=self.final)

    def close(self):
        if not self.drained():
            raise RuntimeError('Cannot close a live native network')
        self.final = self.client.close()['final']

    def abort(self):
        self.client.abort()
