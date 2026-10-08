"""Absolute-time native adapters. A callback makes a response ready, never delivered."""
from collections import Counter


class IdealBanks:
    boundary = 'memory_word_ready_before_explicit_HB'

    def __init__(self, spec):
        self.spec = spec
        self.pending = {}
        self.bank_free = Counter()
        self.last_ps = -1
        self.accepted = self.completed = self.rejected = 0
        self.native_words = 0

    def submit(self, request, now):
        if now % self.spec.dram_period_ps:
            return False
        banks = next(m.banks for m in self.spec.memories if m.id == request.memory)
        counts = Counter((request.memory, (request.bank+i) % banks) for i in range(request.size_bytes//32))
        if any(self.bank_free[bank] > now for bank in counts):
            self.rejected += 1
            return False
        if request.id in self.pending:
            raise RuntimeError('Repeated native transaction')
        self.pending[request.id] = now+(max(counts.values())-1+self.spec.ideal_dram_cycles)*self.spec.dram_period_ps
        # Independent, pipelined bank reference: one word per bank clock.
        for bank, count in counts.items():
            self.bank_free[bank] = now+count*self.spec.dram_period_ps
        self.native_words += request.size_bytes//32
        self.accepted += 1
        return True

    def advance(self, now):
        if now < self.last_ps:
            raise ValueError('Nonmonotonic global time')
        self.last_ps = now
        result = sorted(key for key, at in self.pending.items() if at <= now)
        for key in result:
            del self.pending[key]
            self.completed += 1
        return result

    def record(self):
        return dict(kind='ideal_independent_banks', boundary=self.boundary,
                    accepted=self.accepted, completed=self.completed, rejected=self.rejected,
                    pending=len(self.pending), native_words=self.native_words,
                    dram_period_ps=self.spec.dram_period_ps)


class RamulatorAbsolute:
    """Reuse pinned profile/bridge with ps time, without v1's bandwidth-derived slot.

    HBM2 callback is at the controller after native data transfer. Explicit home
    HB is replaced by that backend boundary, not charged a second time. This
    profile cannot model a pre-controller direct-return branch.
    """
    boundary = 'controller_payload_ready_after_native_bus'

    def __init__(self, spec):
        from w2w.service.dram.ramulator import RamulatorHBM2
        if spec.dram_period_ps != 1000 or any(m.banks != 32 or m.capacity_bytes != 512*1024**2
                                             for m in spec.memories):
            raise ValueError('Native HBM2 reference requires 1000 ps and 32 banks/512 MiB per memory')
        self.backend = RamulatorHBM2(len(spec.memories), slot_ps=1)
        self.channels = {m.id: i for i, m in enumerate(spec.memories)}
        self.tickets = {}
        self.groups = {}
        self.group_accepted = self.group_completed = 0

    def submit(self, request, now):
        if now % 1000:
            return False
        if request.size_bytes != 32:
            if request.id in self.groups:
                raise RuntimeError('Repeated grouped native request')
            self.groups[request.id] = dict(request=request, issued=0, completed=0,
                                           words=request.size_bytes//32)
            self.group_accepted += 1
            return True
        ticket = self.backend.submit(dict(bank=self.channels[request.memory]*32+request.bank,
                                          address=request.word_address))
        if ticket is None:
            return False
        self.tickets[ticket] = request.id
        return True

    def advance(self, now):
        result = []
        for ticket in self.backend.advance(now):
            key = self.tickets.pop(ticket)
            if key not in self.groups:
                result.append(key)
                continue
            row = self.groups[key]
            row['completed'] += 1
            if row['completed'] == row['words']:
                result.append(key)
                del self.groups[key]
                self.group_completed += 1
        # MC expands a descriptor to its exact contiguous, bank-interleaved
        # native addresses. Queue rejection retains the unissued word. Limit
        # expansion to 32 words/channel/tCK; DRAM commands still belong to Ramulator.
        if now % 1000 == 0:
            issued, blocked = Counter(), set()
            for key, row in self.groups.items():
                req = row['request']
                start = req.word_address*32+req.bank
                while row['issued'] < row['words'] and issued[req.memory] < 32 and req.memory not in blocked:
                    word = start+row['issued']
                    ticket = self.backend.submit(dict(bank=self.channels[req.memory]*32+word%32,
                                                      address=word//32))
                    if ticket is None:
                        blocked.add(req.memory)
                        break
                    self.tickets[ticket] = key
                    row['issued'] += 1
                    issued[req.memory] += 1
        return result

    def record(self):
        result = self.backend.record()
        result.update(boundary=self.boundary, accepted=self.backend.accepted,
                      completed=self.backend.completed, pending=len(self.tickets)+len(self.groups),
                      grouped_descriptors_accepted=self.group_accepted,
                      grouped_descriptors_completed=self.group_completed,
                      grouped_expansion_words_per_channel_cycle=32)
        return result

    def close(self):
        self.backend.close()
