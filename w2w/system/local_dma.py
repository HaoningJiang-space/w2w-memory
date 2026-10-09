"""Local transfer serialization, independent of the native NoC process.

The caller retains finite NI admission and packet lifetime. This component owns
only serial channel availability and preserves both declared local contracts.
HB segments use the same existing channel-key namespace as local DMA sources.
"""
from collections import Counter


class LocalDma:
    def __init__(self, spec):
        self.spec = spec
        self.free = Counter()

    def reserve(self, channel, now, beats, period_ps):
        first = max(now, self.free[channel])
        self.free[channel] = first + beats*period_ps
        return first

    def payload_beats(self, packet, supplied, eligible, now):
        width = self.spec.rx_write_bytes_per_cycle
        rows = []
        for ordinal in range(supplied, eligible):
            size = min(width, max(0, packet.payload_bytes-ordinal*width))
            first = self.reserve(packet.src, now, 1, self.spec.noc_period_ps)
            rows.append((first+self.spec.noc_period_ps, size))
        return rows

    def legacy_fragments(self, packet, supplied, eligible, now):
        rows = []
        for ordinal in range(supplied, eligible):
            first = ordinal*self.spec.flit_bytes
            size = max(0, min(first+self.spec.flit_bytes, packet.payload_bytes+self.spec.header_bytes)
                       -max(first, self.spec.header_bytes))
            start = self.reserve(packet.src, now, 1, self.spec.noc_period_ps)
            rows.append((start+self.spec.noc_period_ps, size))
        return rows
