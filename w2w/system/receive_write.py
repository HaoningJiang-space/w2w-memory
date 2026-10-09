"""One shared SRAM receive write port per aggregate tile.

Local DMA, remote responses and activations consume this same service. The
caller decides whether bytes target SRAM and maintains packet/credit lifetime.
"""
from collections import Counter
from math import ceil


class ReceiveWritePort:
    def __init__(self, bytes_per_cycle, period_ps):
        self.bytes_per_cycle, self.period_ps = bytes_per_cycle, period_ps
        self.free = Counter()
        self.bytes, self.cycles, self.wait_ps = Counter(), Counter(), Counter()
        self.cycles_by_class = Counter()

    def reserve(self, tile, traffic_class, size, at):
        start = max(at, self.free[tile])
        cycles = ceil(size/self.bytes_per_cycle)
        finish = start+cycles*self.period_ps
        self.free[tile] = finish
        self.bytes[tile] += size
        self.cycles[tile] += cycles
        self.cycles_by_class[tile+'/'+traffic_class] += cycles
        self.wait_ps[tile] += start-at
        return finish, cycles, start-at
