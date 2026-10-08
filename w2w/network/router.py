"""Streaming flits, per-class input queues, shared physical outputs, delayed credits.

One router traversal per flit; a VC output is held through a packet's tail.
All choices use the old queue state, then commit together. Packets are bounded
at NI acceptance. This is a small deterministic model, not a BookSim wrapper.
"""
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
import heapq
from math import ceil
from w2w.domain.protocol import TRAFFIC_CLASSES


@dataclass
class Flit:
    packet: object
    index: int
    count: int
    hop: int
    ready_ps: int


class CreditNetwork:
    def __init__(self, builder, events=None):
        self.builder, self.spec = builder, builder.spec
        self.events = events if events is not None else []
        self.queues = {}
        self.credits = {}
        self.flight = Counter()
        self.returning = Counter()
        self.future = []
        self.serial = 0
        self.locks = {}
        self.rr = Counter()
        self.assembly = {}
        self.completed = defaultdict(deque)
        self.rx_occupied = Counter()
        self.ids = set()
        self.retired = set()
        self.link_flits = Counter()
        self.accepted_bytes = Counter()
        self.delivered_bytes = Counter()
        self.peak_queue = Counter()
        self.rejections = 0
        self.last_step = -1
        for node in (*builder.tiles, *builder.memories):
            for cls in TRAFFIC_CLASSES:
                self.queues[node, 'NI', cls] = deque()
        for link in self.spec.links:
            for cls in TRAFFIC_CLASSES:
                self.queues[link.dst, link.id, cls] = deque()
                self.credits[link.id, cls] = self.spec.input_buffer_flits

    def log(self, now, kind, **values):
        self.events.append(dict(time_ps=now, kind=kind, **values))

    def try_send(self, packet, now):
        if packet.id in self.ids:
            raise ValueError('Duplicate accepted packet identity')
        if packet.traffic_class not in TRAFFIC_CLASSES:
            raise ValueError('Unsupported virtual network')
        if type(packet.payload_bytes) is not int or not 0 <= packet.payload_bytes <= self.spec.packet_payload_bytes:
            raise ValueError('Packet exceeds the registered bounded payload')
        if packet.route != self.builder.route(packet.src, packet.dst):
            raise ValueError('Packet route is not the executable dimensional route')
        count = ceil((packet.payload_bytes+self.spec.header_bytes)/self.spec.flit_bytes)
        key = packet.src, 'NI', packet.traffic_class
        queue = self.queues[key]
        if len(queue)+count > self.spec.injection_flits:
            self.rejections += 1
            return False
        ready = now + self.spec.router_cycles*self.spec.noc_period_ps
        queue.extend(Flit(packet, i, count, 0, ready) for i in range(count))
        self.ids.add(packet.id)
        self.accepted_bytes[packet.traffic_class] += packet.payload_bytes
        self.peak_queue[key] = max(self.peak_queue[key], len(queue))
        self.log(now, 'packet_accept', packet=packet.id, src=packet.src, dst=packet.dst,
                 traffic_class=packet.traffic_class, payload_bytes=packet.payload_bytes, flits=count)
        return True

    def _later(self, at, kind, key, value=None):
        self.serial += 1
        heapq.heappush(self.future, (at, self.serial, kind, key, value))

    def arrive(self, now):
        while self.future and self.future[0][0] <= now:
            at, _, kind, key, value = heapq.heappop(self.future)
            if kind == 'credit':
                self.returning[key] -= 1
                self.credits[key] += 1
            else:
                link = self.builder.links[key[0]]
                self.flight[key] -= 1
                value.ready_ps = at + self.spec.router_cycles*self.spec.noc_period_ps
                qkey = link.dst, link.id, key[1]
                self.queues[qkey].append(value)
                self.peak_queue[qkey] = max(self.peak_queue[qkey], len(self.queues[qkey]))
        self.check()

    def _release(self, key, now):
        _, port, cls = key
        if port != 'NI':
            credit_key = port, cls
            self.returning[credit_key] += 1
            self._later(now+self.builder.links[port].credit_cycles*self.spec.noc_period_ps,
                        'credit', credit_key)

    def step(self, now):
        if now % self.spec.noc_period_ps or now <= self.last_step:
            raise ValueError('Network ticks must be monotonic clock boundaries')
        self.last_step = now
        candidates = defaultdict(list)
        for key, queue in self.queues.items():
            if not queue or queue[0].ready_ps > now:
                continue
            flit = queue[0]
            packet = flit.packet
            if flit.hop == len(packet.route):
                rxkey = packet.dst, packet.traffic_class
                if flit.index == 0 and self.rx_occupied[rxkey] >= self.spec.ejection_packets:
                    continue
                output = 'EJECT', packet.dst
            else:
                link_id = packet.route[flit.hop]
                ckey = link_id, packet.traffic_class
                if not self.credits[ckey] or self.locks.get(ckey, packet.id) != packet.id:
                    continue
                output = 'LINK', link_id
            candidates[output].append(key)
        actions, used_inputs = [], set()
        for output in sorted(candidates):
            keys = sorted(candidates[output])
            # Round robin over the fixed input port/class order, not Python insertion order.
            all_keys = sorted(self.queues)
            start = self.rr[output] % len(all_keys)
            keys.sort(key=lambda k: (all_keys.index(k)-start) % len(all_keys))
            for key in keys:
                physical_input = key[:2]
                if physical_input in used_inputs:
                    continue
                actions.append((output, key))
                used_inputs.add(physical_input)
                self.rr[output] = all_keys.index(key)+1
                break
        for output, key in actions:
            flit = self.queues[key].popleft()
            self._release(key, now)
            packet = flit.packet
            if output[0] == 'EJECT':
                rxkey = packet.dst, packet.traffic_class
                if flit.index == 0:
                    self.rx_occupied[rxkey] += 1
                    self.assembly[packet.id] = 0
                if self.assembly.get(packet.id) != flit.index:
                    raise RuntimeError('Out-of-order or duplicate packet flit')
                self.assembly[packet.id] += 1
                if flit.index == flit.count-1:
                    del self.assembly[packet.id]
                    self.completed[rxkey].append(packet)
            else:
                link = self.builder.links[output[1]]
                ckey = link.id, packet.traffic_class
                self.credits[ckey] -= 1
                self.flight[ckey] += 1
                self.locks[ckey] = packet.id
                if flit.index == flit.count-1:
                    del self.locks[ckey]
                flit.hop += 1
                self.link_flits[link.id] += 1
                self.log(now, 'link_send', link=link.id, resource=link.resource_id,
                         packet=packet.id, flit=flit.index, traffic_class=packet.traffic_class)
                self._later(now+link.pipeline_cycles*self.spec.noc_period_ps, 'arrival', ckey, flit)
        self.check()

    def deliver(self, now, accept):
        """Ejection storage is freed only when the endpoint accepts a whole packet."""
        for key in sorted(self.completed):
            queue = self.completed[key]
            if queue and accept(queue[0]):
                packet = queue.popleft()
                self.rx_occupied[key] -= 1
                self.retired.add(packet.id)
                self.delivered_bytes[packet.traffic_class] += packet.payload_bytes
                self.log(now, 'packet_deliver', packet=packet.id, src=packet.src, dst=packet.dst,
                         traffic_class=packet.traffic_class, payload_bytes=packet.payload_bytes)

    def check(self):
        for link in self.spec.links:
            for cls in TRAFFIC_CLASSES:
                key = link.id, cls
                occupied = len(self.queues[link.dst, link.id, cls])
                if (self.credits[key] < 0 or occupied > self.spec.input_buffer_flits
                        or self.credits[key]+occupied+self.flight[key]+self.returning[key]
                        != self.spec.input_buffer_flits):
                    raise RuntimeError('Flit/credit conservation failure')
        if any(v < 0 or v > self.spec.ejection_packets for v in self.rx_occupied.values()):
            raise RuntimeError('Ejection storage exceeded')

    def drained(self):
        return (self.ids == self.retired and not self.future and not self.locks
                and not self.assembly and not any(self.rx_occupied.values())
                and not any(self.queues.values()) and not any(self.completed.values()))

    def record(self):
        return dict(accepted_packets=len(self.ids), delivered_packets=len(self.retired),
                    payload_bytes=dict(self.delivered_bytes), link_flits=dict(self.link_flits),
                    link_wire_bytes={k: v*self.spec.flit_bytes for k, v in self.link_flits.items()},
                    injection_rejections=self.rejections,
                    peak_input_flits={'/'.join(k): v for k, v in self.peak_queue.items()},
                    drained=self.drained())
