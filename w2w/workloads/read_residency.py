"""Compile fractional residence into one frozen address-to-bank mapping."""
from bisect import bisect_left
from collections import Counter
from dataclasses import asdict
from fractions import Fraction
from math import gcd, lcm

from w2w.service.evaluator import CandidateEvaluator
from w2w.workloads.read_trace import digest


def stripe_period(shares, maximum=65536):
    """Smooth weighted round robin with exact rational counts, frozen once."""
    weights = [(bank, Fraction(value).limit_denominator(maximum))
               for bank, value in enumerate(shares) if value]
    if (not weights or sum(v for _, v in weights) != 1
            or any(abs(float(v) - shares[b]) > 1e-12 for b, v in weights)):
        raise ValueError('Residence fractions do not have a bounded exact rational period')
    denominator = lcm(*(v.denominator for _, v in weights))
    if denominator > maximum:
        raise ValueError('Residence period exceeds the registered bound')
    counts = [(b, int(v * denominator)) for b, v in weights]
    scale = gcd(*(n for _, n in counts))
    counts = [(b, n // scale) for b, n in counts]
    total = sum(n for _, n in counts)
    credit = dict.fromkeys((b for b, _ in counts), 0)
    result = []
    for _ in range(total):
        for b, n in counts:
            credit[b] += n
        bank = max(credit, key=lambda b: (credit[b], -b))
        credit[bank] -= total
        result.append(bank)
    if Counter(result) != dict(counts):
        raise RuntimeError('Stripe compilation failed exact conservation')
    return tuple(result)


class ReadResidency:
    """Address mapping and physical legality; no per-task remapping or copying.

    Mapping storage is O(objects * used banks + compute * stripe period).
    Local bank addresses are disjoint even for different-size object tails.
    """
    def __init__(self, design, trace):
        if design.endpoint.word_bits != trace.word_bytes * 8:
            raise ValueError('Trace word size and native interface disagree')
        self.design, self.trace = design, trace
        self.evaluator = CandidateEvaluator(design)
        self.fabric = self.evaluator.f
        nc = len(design.geometry.compute_xy)
        if (any(o.compute >= nc for o in trace.objects)
                or any(t.compute is not None and t.compute >= nc for t in trace.tasks)):
            raise ValueError('Compute outside the frozen fabric')
        self.periods = tuple(stripe_period(row) for row in design.layout.shares)
        self.positions = tuple({b: tuple(i for i, v in enumerate(period) if v == b)
                                for b in set(period)} for period in self.periods)
        self.objects = {o.id: o for o in trace.objects}
        self.base = {}
        self.bank_words = [0] * len(design.layout.shares[0])
        for obj in sorted(trace.objects, key=lambda o: o.id):
            for bank, words in self.count(obj.id, 0, obj.size_bytes // trace.word_bytes).items():
                self.base[obj.id, bank] = self.bank_words[bank]
                self.bank_words[bank] += words
        if any(v * trace.word_bytes > design.exposure.bank_capacity_gib * 2**30
               for v in self.bank_words):
            raise ValueError('Actual logical object placement exceeds bank capacity')
        self.sha256 = digest(self.record())

    def count(self, object_id, first_word, count):
        obj = self.objects[object_id]
        period = self.periods[obj.compute]
        def prefix(stop, positions):
            turns, tail = divmod(stop, len(period))
            return turns * len(positions) + bisect_left(positions, tail)
        return {b: n for b, positions in self.positions[obj.compute].items()
                if (n := prefix(first_word + count, positions) - prefix(first_word, positions))}

    def locate(self, object_id, word):
        obj = self.objects[object_id]
        if type(word) is not int or not 0 <= word < obj.size_bytes // self.trace.word_bytes:
            raise ValueError('Word outside object')
        turns, index = divmod(word, len(self.periods[obj.compute]))
        bank = self.periods[obj.compute][index]
        positions = self.positions[obj.compute][bank]
        address = self.base[obj.id, bank] + turns * len(positions) + bisect_left(positions, index)
        edge = self.fabric.paths[obj.compute, bank][0]
        port = self.fabric.edges[edge]['mp']
        return bank, address, port, edge

    def task_bytes(self, task):
        banks = Counter()
        for read in task.reads:
            banks.update({b: n * self.trace.word_bytes for b, n in self.count(
                read.object, read.offset_bytes // self.trace.word_bytes,
                read.size_bytes // self.trace.word_bytes).items()})
        return dict(sorted(banks.items()))

    def record(self):
        # Deliberately excludes endpoint duplication: identical residence should
        # have the same fingerprint for the implementation ablation.
        return dict(schema='w2w.read-residency.v1', algorithm='smooth_integer_striping_v1',
                    geometry=asdict(self.design.geometry), exposure=asdict(self.design.exposure),
                    fractional_layout_sha256=self.design.layout.sha256,
                    word_bytes=self.trace.word_bytes,
                    objects=[asdict(o) for o in sorted(self.trace.objects, key=lambda o: o.id)],
                    periods=self.periods, bank_resident_words=self.bank_words)
