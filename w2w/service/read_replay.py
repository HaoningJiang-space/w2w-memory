"""Bounded closed-loop read-return model with explicit request and RX credits.

This is a word/bit-budget system model, not an RTL or DRAM timing simulator.
There is one native admission per bank slot. Accepted native returns reserve
source storage until serialized; partial words reserve finite RX storage.
"""
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from hashlib import sha256
import json

from w2w.workloads.read_residency import ReadResidency
from w2w.workloads.read_trace import digest, integer


@dataclass(frozen=True)
class ReadReplayConfig:
    request_latency_slots: int = 1
    native_latency_slots: int = 0
    link_latency_slots: int = 1
    request_words_per_compute_slot: int = 64
    outstanding_words_per_compute: int = 128
    rx_depth_words: int = 2
    rx_ready: tuple = (1,)
    max_slots: int = 100000
    max_trace_words: int = 10000000

    def __post_init__(self):
        object.__setattr__(self, 'rx_ready', tuple(self.rx_ready))
        for key in ('request_latency_slots', 'native_latency_slots', 'link_latency_slots'):
            integer(getattr(self, key), key)
        for key in ('request_words_per_compute_slot', 'outstanding_words_per_compute',
                    'rx_depth_words', 'max_slots', 'max_trace_words'):
            integer(getattr(self, key), key, 1)
        if not self.rx_ready or any(type(v) is not int or v not in (0, 1) for v in self.rx_ready):
            raise ValueError('RX readiness must be an explicit binary period')


def design_record(design):
    row = asdict(design)
    row['home_fraction'] = str(design.home_fraction)
    return row


def replay_reads(design, trace, config=ReadReplayConfig()):
    residence = ReadResidency(design, trace)
    spec = design.endpoint
    task_by_id = {t.id: t for t in trace.tasks}
    words = {t.id: sum(r.size_bytes for r in t.reads) // trace.word_bytes for t in trace.tasks}
    expected = sum(words.values())
    if expected > config.max_trace_words:
        raise ValueError('Trace exceeds registered replay word limit; no implicit sampling')
    nc = len(design.geometry.compute_xy)
    state = {}
    active = {}
    finished = {}
    not_started = set(task_by_id)
    pending = defaultdict(lambda: defaultdict(deque))
    source = defaultdict(deque)
    receiver = defaultdict(deque)
    ports_by_bank = defaultdict(set)
    for compute, bank in residence.evaluator.ports:
        ports_by_bank[bank].add(residence.evaluator.ports[compute, bank])
    cursor = Counter()
    outstanding = [0] * nc
    peak_outstanding = [0] * nc
    peak_source = Counter()
    peak_rx = Counter()
    native_by_bank = Counter()
    sent_by_route = Counter()
    received_by_route = Counter()
    blocked = Counter()
    issued = admitted = transmitted = delivered = sent_bits = 0
    delivery_hash = sha256()
    last_slot = 0

    for tick in range(config.max_slots + 1):
        # Completion at a slot boundary feeds the DAG before issuing new work.
        if config.rx_ready[tick % len(config.rx_ready)]:
            for key in sorted(receiver):
                q = receiver[key]
                if q and q[0]['complete_at'] is not None and q[0]['complete_at'] <= tick:
                    item = q.popleft()
                    request = item['request']
                    t = task_by_id[request['task']]
                    outstanding[t.compute] -= 1
                    delivered += 1
                    received_by_route[key] += 1
                    s = state[t.id]
                    s['remaining'] -= 1
                    delivery_hash.update(json.dumps([tick, t.id, *request['logical'],
                                                      request['bank'], request['address']],
                                                     separators=(',', ':')).encode() + b'\n')
                    if s['remaining'] == 0:
                        s['reads_done'] = tick
                        s['finish'] = tick + t.compute_slots
        # Zero-duration barriers can unlock other barriers in this same boundary.
        while True:
            changed = False
            for key, s in state.items():
                if key not in finished and s['finish'] is not None and s['finish'] <= tick:
                    finished[key] = s['finish']
                    c = task_by_id[key].compute
                    if c is not None:
                        del active[c]
                    changed = True
            candidates = []
            for key in sorted(not_started):
                t = task_by_id[key]
                if (t.release_slot > tick or any(d not in finished for d in t.dependencies)
                        or (t.compute is not None and t.compute in active)):
                    continue
                candidates.append(key)
            # Resolve instantaneous joins before arbitrating compute ownership.
            # Otherwise a task behind a zero-time join can lose priority solely
            # because the join's lexical ID sorts after another ready task.
            instant = [key for key in candidates
                       if not words[key] and not task_by_id[key].compute_slots]
            for key in instant or candidates:
                t = task_by_id[key]
                if t.compute is not None and t.compute in active:
                    continue
                ready_at = max((t.release_slot, *(finished[d] for d in t.dependencies)))
                state[key] = dict(start=tick, eligible=ready_at, remaining=words[key], issued=0,
                                  iterator=trace.words(t), reads_done=tick if not words[key] else None,
                                  finish=tick + t.compute_slots if not words[key] else None)
                not_started.remove(key)
                if t.compute is not None:
                    active[t.compute] = key
                changed = True
            if not changed:
                break
        if len(finished) == len(trace.tasks):
            last_slot = tick
            break
        if tick == config.max_slots:
            incomplete = sorted(set(task_by_id) - set(finished))
            raise RuntimeError(f'Replay slot limit reached with {len(incomplete)} incomplete tasks; '
                               f'first={incomplete[:4]}, issued={issued}, delivered={delivered}')

        # Addresses take an explicit request latency to reach their memory owner.
        # The outstanding cap also bounds the sum of all memory request queues.
        for c, key in sorted(active.items()):
            s = state[key]
            budget = min(config.request_words_per_compute_slot,
                         config.outstanding_words_per_compute - outstanding[c], words[key] - s['issued'])
            if budget == 0 and s['issued'] < words[key]:
                blocked['outstanding_compute_slots'] += 1
            for _ in range(budget):
                logical = next(s['iterator'])
                bank, address, port, edge = residence.locate(*logical)
                pending[bank][port].append(dict(task=key, logical=logical, bank=bank,
                                                address=address, port=port, edge=edge,
                                                eligible=tick + config.request_latency_slots))
                s['issued'] += 1
                issued += 1
                outstanding[c] += 1
            peak_outstanding[c] = max(peak_outstanding[c], outstanding[c])

        # Frozen weighted arbitration skips empty/unarrived ports. A selected
        # request cannot bypass a full destination queue. No active-mask oracle.
        for bank in sorted(pending):
            if not spec.native.ready[tick % len(spec.native.ready)]:
                if any(pending[bank].values()):
                    blocked['native_unavailable_bank_slots'] += 1
                continue
            sequence = residence.evaluator.sequences[bank]
            for offset in range(len(sequence)):
                index = (cursor[bank] + offset) % len(sequence)
                p = sequence[index]
                requests = pending[bank][p]
                if not requests or requests[0]['eligible'] > tick:
                    continue
                cursor[bank] = index
                occupancy = (sum(len(source[bank, v]) for v in ports_by_bank[bank])
                             if spec.mode == 'direct' else len(source[bank, p]))
                capacity = 1 if spec.mode == 'direct' else spec.depths[p]
                if occupancy >= capacity:
                    blocked['source_full_bank_slots'] += 1
                    break
                request = requests.popleft()
                source[bank, p].append(dict(request=request, remaining=spec.word_bits,
                                            ready_at=tick + config.native_latency_slots, rx=None))
                admitted += 1
                native_by_bank[bank] += 1
                cursor[bank] = (index + 1) % len(sequence)
                peak_source[bank, p] = max(peak_source[bank, p], len(source[bank, p]))
                break

        # Port peaks were certified against HB, memory/compute ports and
        # controller capacities before replay. RX credits can only lower them.
        for key in sorted(source):
            q = source[key]
            budget = spec.widths[key[1]]
            while budget and q and q[0]['ready_at'] <= tick:
                item = q[0]
                if item['rx'] is None:
                    if len(receiver[key]) >= config.rx_depth_words:
                        blocked['rx_full_output_slots'] += 1
                        break
                    item['rx'] = dict(request=item['request'], complete_at=None)
                    receiver[key].append(item['rx'])
                    peak_rx[key] = max(peak_rx[key], len(receiver[key]))
                amount = min(budget, item['remaining'])
                item['remaining'] -= amount
                budget -= amount
                sent_bits += amount
                sent_by_route[key] += amount
                if item['remaining'] == 0:
                    item['rx']['complete_at'] = tick + config.link_latency_slots + 1
                    q.popleft()
                    transmitted += 1

        # Separate incomplete native words from partially assembled RX words:
        # partial words appear in both but must never be counted twice.
        live_source = sum(map(len, source.values()))
        live_requests = sum(len(q) for ps in pending.values() for q in ps.values())
        complete_rx = sum(item['complete_at'] is not None for q in receiver.values() for item in q)
        if (issued != delivered + live_requests + live_source + complete_rx
                or admitted != transmitted + live_source or transmitted != delivered + complete_rx
                or admitted * spec.word_bits != sent_bits + sum(item['remaining']
                                                         for q in source.values() for item in q)
                or sum(outstanding) != issued - delivered
                or any(v < 0 or v > config.outstanding_words_per_compute for v in outstanding)
                or any(len(q) > config.rx_depth_words for q in receiver.values())):
            raise RuntimeError('Per-slot request/word/bit/credit conservation failure')
    else:
        raise RuntimeError('Replay did not complete')

    if not (expected == issued == admitted == transmitted == delivered
            and sent_bits == expected * spec.word_bits and not any(outstanding)):
        raise RuntimeError('Final read conservation failure')
    if residence.sha256 != digest(residence.record()):
        raise RuntimeError('Frozen address mapping changed during execution')
    slot_ns = spec.word_bits / (8000 * design.exposure.bank_bw)
    tasks = []
    for task in trace.tasks:
        s = state[task.id]
        bank_bytes = residence.task_bytes(task)
        total_bytes = sum(bank_bytes.values())
        memory_bytes = Counter()
        for b, count in bank_bytes.items():
            memory_bytes[b // len(design.exposure.mask)] += count
        tasks.append(dict(id=task.id, compute=task.compute, start_slot=s['start'],
                          reads_done_slot=s['reads_done'], finish_slot=s['finish'],
                          compute_queue_slots=s['start'] - s['eligible'],
                          read_wait_slots=s['reads_done'] - s['start'],
                          logical_bytes=total_bytes, bank_bytes=bank_bytes,
                          memory_byte_fractions={m: n / total_bytes for m, n in memory_bytes.items()}))
    routes = [dict(bank=b, port=p, sent_bits=sent_by_route[b, p],
                   received_words=received_by_route[b, p], peak_source_words=peak_source[b, p],
                   peak_rx_words=peak_rx[b, p],
                   tx_utilization=sent_by_route[b, p] / (last_slot * spec.widths[p]) if last_slot else 0.)
              for b, p in sorted(sent_by_route)]
    return dict(schema='w2w.read-replay.v1', trace_sha256=trace.sha256,
                design_sha256=digest(design_record(design)), residence_sha256=residence.sha256,
                design=design_record(design), residence=residence.record(), config=asdict(config),
                evidence=trace.evidence, source=trace.source,
                scope='Finite word/bit-budget dependency replay; uncalibrated request/native/link timing; '
                      'no payload simulation, RTL cycle equivalence, DRAM timing or application speedup claim',
                slot_ns=slot_ns, makespan_slots=last_slot, makespan_ns=last_slot * slot_ns,
                logical_bytes=expected * trace.word_bytes,
                effective_tb_s=expected * trace.word_bytes / (last_slot * slot_ns * 1000) if last_slot else 0.,
                summed_task_read_wait_slots=sum(t['read_wait_slots'] for t in tasks),
                tasks=tasks, routes=routes, stalls=dict(blocked),
                native_words_by_bank=dict(native_by_bank), peak_outstanding_words=peak_outstanding,
                delivery_sha256=delivery_hash.hexdigest(), composition=residence.evaluator.composition,
                audit=dict(issued_words=issued, admitted_words=admitted, transmitted_words=transmitted,
                           delivered_words=delivered, sent_bits=sent_bits,
                           every_slot_conserved=True, frozen_residence=True))
