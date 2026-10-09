"""Pinned HBM2 command-timing reference, not a calibrated WoW DRAM macro.

One reference channel per memory: 2 pseudochannels, 32 banks, 32-byte bursts.
No implicit burst splitting, address truncation, profile scaling or downloads.
"""
from fractions import Fraction
from functools import lru_cache
from hashlib import sha256
import importlib.util
import math
import os
from pathlib import Path

from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.validators import integer

UPSTREAM_COMMIT = '72427a1bba3771564c4fb0e494ba02242fd1eaa7'
BANK_WORDS = 1 << 19


@lru_cache(maxsize=1)
def load_bridge():
    path = Path(os.environ.get('W2W_RAMULATOR_BRIDGE', ''))
    if not path.is_file():
        raise RuntimeError('Set W2W_RAMULATOR_BRIDGE to the built pinned native extension')
    spec = importlib.util.spec_from_file_location('_w2w_ramulator', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.upstream_commit != UPSTREAM_COMMIT:
        raise RuntimeError('Unregistered Ramulator revision')
    return module, path


def reference_config(memories, queue_depth=32, refresh=True, command_trace=None):
    import ramulator
    integer(memories, 'memory channels', 1)
    integer(queue_depth, 'controller queue depth', 1)
    dram = ramulator.dram.HBM2(org_preset='HBM2_2Gb', timing_preset='HBM2_2000Mbps')
    controllers = []
    for _ in range(memories):
        plugins = ([] if command_trace is None else
                   [ramulator.controller_plugin.CmdTraceRecorder(path=str(command_trace))])
        controllers.append(ramulator.controller.HBM12(
            dram=dram, scheduler=ramulator.scheduler.FRFCFS(),
            refresh_manager=(ramulator.refresh_manager.AllBank() if refresh else
                             ramulator.refresh_manager.NoRefresh()),
            row_policy=ramulator.row_policy.Open(),
            addr_mapper=ramulator.addr_mapper.PassThroughAddrMapper(),
            read_buffer_size=queue_depth, controller_plugins=plugins))
    memory = ramulator.memory_system.GenericDRAM(
        clock_ratio=1, controllers=controllers,
        channel_mapper=ramulator.channel_mapper.PassThroughChannelMapper())
    return {'frontend': ramulator.frontend.External(clock_ratio=1).to_config(),
            'memory_system': memory.to_config()}


class RamulatorHBM2:
    def __init__(self, memories, slot_ps=1024, queue_depth=32, refresh=True, command_trace=None):
        integer(slot_ps, 'endpoint slot picoseconds', 1)
        self.memories, self.slot_ps = memories, slot_ps
        self.config = reference_config(memories, queue_depth, refresh, command_trace)
        self.tck_ps = 1000
        bridge, path = load_bridge()
        self.impl = bridge.IncrementalMemory(self.config)
        self.bridge_sha256 = sha256(path.read_bytes()).hexdigest()
        self.next_id = self.accepted = self.completed = self.rejected = 0
        self.pending = set()
        self.last_tick = 0

    def validate(self, design, trace, config, residence):
        period = Fraction(design.endpoint.word_bits * 1000, 8000) / Fraction(str(design.exposure.bank_bw))
        if (len(design.exposure.mask) != 32 or trace.word_bytes != 32 or
                len(design.geometry.memory_xy) != self.memories or period != self.slot_ps):
            raise ValueError('HBM2 reference requires 32 banks/M, 32-byte words and matching clocks')
        if design.endpoint.native.ready != (1,) or config.native_latency_slots != 0:
            raise ValueError('Do not compose periodic/fixed native timing with DRAM commands')
        if any(words > BANK_WORDS for words in residence.bank_words):
            raise ValueError('Frozen data exceed 16 MiB per reference HBM2 bank')
        if self.accepted or self.last_tick:
            raise ValueError('Use a fresh backend per replay')

    def submit(self, request):
        bank, address = request['bank'], request['address']
        if not 0 <= bank < self.memories * 32 or not 0 <= address < BANK_WORDS:
            raise ValueError('Out-of-range physical DRAM address')
        ticket = self.next_id
        if not self.impl.send(ticket, bank, address):
            self.rejected += 1
            return None
        self.next_id += 1
        self.accepted += 1
        self.pending.add(ticket)
        return ticket

    def advance(self, tick):
        if tick < self.last_tick:
            raise ValueError('Nonmonotonic endpoint clock')
        self.last_tick = tick
        completions = self.impl.advance(tick * self.slot_ps // self.tck_ps)
        result = []
        for ticket, cycle in completions:
            if ticket not in self.pending or cycle * self.tck_ps > tick * self.slot_ps:
                raise RuntimeError('Invalid native completion')
            self.pending.remove(ticket)
            result.append(ticket)
            self.completed += 1
        return result

    def record(self):
        def finite(value):
            if isinstance(value, dict): return {k: finite(v) for k, v in value.items()}
            if isinstance(value, list): return [finite(v) for v in value]
            if isinstance(value, float) and not math.isfinite(value): return None
            return value
        return dict(kind='ramulator_hbm2_reference_v1', upstream_commit=UPSTREAM_COMMIT,
                    bridge_sha256=self.bridge_sha256, config=self.config,
                    config_sha256=digest(self.config), tck_ps=self.tck_ps, slot_ps=self.slot_ps,
                    accepted_words=self.accepted, completed_words=self.completed,
                    rejected_attempts=self.rejected, pending_words=len(self.pending),
                    upstream_pending=self.impl.outstanding(), stats=finite(self.impl.stats()),
                    scope='Public HBM2 command model; preset contains upstream timing estimates; '
                          'one 512 MiB channel/M; not calibrated WoW DRAM or signoff')

    def close(self):
        self.impl.close()
