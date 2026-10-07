"""Exact periodic service of an always-ready isolated word-return path."""
from collections import deque
from fractions import Fraction
from math import gcd


def packed_rx_requirement(word_bits, width, link_latency):
    """Necessary RX words for continuous full-width packing, including phase."""
    if not 0 < width <= word_bits or link_latency < 0:
        raise ValueError('Invalid width or link delay')
    divisor = gcd(word_bits, width)
    spans = [(word_bits + (k * word_bits) % width + width - 1) // width
             for k in range(width // divisor)]
    mean_span = Fraction(sum(spans), len(spans))
    occupancy = Fraction(width, word_bits) * (mean_span + link_latency)
    return dict(packing_words=len(spans), beat_spans=spans, mean_beat_span=str(mean_span),
                full_width_rate=str(Fraction(width, word_bits)),
                necessary_mean_rx_occupancy=str(occupancy),
                minimum_integer_rx=(occupancy.numerator + occupancy.denominator - 1) // occupancy.denominator)


def return_path_period(width, source_depth, rx_depth, word_bits=256, link_latency=1):
    """One native word/slot, FIFO transmission, whole-word RX reservation.

    This reproduces the existing return ordering without a compute/address
    stream, physical graph or arbitration. State recurrence is the witness.
    """
    if (not 0 < width <= word_bits or source_depth < 1 or rx_depth < 1 or link_latency < 0):
        raise ValueError('Invalid return-path capacity')
    source, receiver = deque(), deque()
    admitted = sent_words = delivered = sent_bits = 0
    seen, history = {}, []
    for tick in range(10000):
        state = (tuple((item['remaining'], item['rx'] is not None) for item in source),
                 tuple(None if item['done'] is None else item['done'] - tick for item in receiver))
        if state in seen:
            first, counts = seen[state]
            period = tick - first
            deltas = [a-b for a, b in zip((admitted, sent_words, delivered, sent_bits), counts)]
            if len(set(deltas[:3])) != 1 or deltas[3] != deltas[0] * word_bits:
                raise ValueError('Periodic path does not conserve complete words')
            return dict(width_bits=width, source_depth=source_depth, rx_depth=rx_depth,
                link_latency=link_latency, warmup_slots=first, period_slots=period,
                delivered_words_per_period=deltas[2], words_per_slot=str(Fraction(deltas[2], period)),
                periodic_states=history[first:tick],
                scope='Exact isolated always-ready return contract; finite shared tasks require replay')
        seen[state] = tick, (admitted, sent_words, delivered, sent_bits)
        history.append(state)
        if receiver and receiver[0]['done'] is not None and receiver[0]['done'] <= tick:
            receiver.popleft()
            delivered += 1
        if len(source) < source_depth:
            source.append(dict(remaining=word_bits, rx=None))
            admitted += 1
        budget = width
        while budget and source:
            item = source[0]
            if item['rx'] is None:
                if len(receiver) == rx_depth:
                    break
                item['rx'] = dict(done=None)
                receiver.append(item['rx'])
            amount = min(budget, item['remaining'])
            item['remaining'] -= amount
            budget -= amount
            sent_bits += amount
            if not item['remaining']:
                item['rx']['done'] = tick + link_latency + 1
                source.popleft()
                sent_words += 1
        if (admitted * word_bits != sent_bits + sum(item['remaining'] for item in source)
                or admitted - delivered != len(source) + sum(item['done'] is not None for item in receiver)):
            raise ValueError('Return-path slot conservation failed')
    raise ValueError('Return path did not reach a repeated state')
