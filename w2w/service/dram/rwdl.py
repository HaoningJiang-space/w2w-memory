"""Native independent arrays; finite shared digital resources are in the adapter."""
from hashlib import sha256
import math

from w2w.service.dram.ramulator import UPSTREAM_COMMIT, load_bridge
from w2w.service.dram.rwdl_spec import W2WRWDL
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.validators import integer


def candidate_config(memories, *, refresh=True, command_trace=None,profile=None):
    import ramulator
    integer(memories, 'memories', 1)
    controllers = []
    for channel in range(memories * 32):
        plugins = ([] if command_trace is None else
                   [ramulator.controller_plugin.CmdTraceRecorder(path=str(command_trace))])
        controller = ramulator.controller.GenericDDR(
            dram=W2WRWDL(org_preset='array128Mbit', timing_preset='candidate3760ps',
                **({} if profile is None else vars(profile.timing))),
            scheduler=ramulator.scheduler.FRFCFS(),
            refresh_manager=ramulator.refresh_manager.NoRefresh(),
            row_policy=ramulator.row_policy.Open(),
            addr_mapper=ramulator.addr_mapper.PassThroughAddrMapper(),
            read_buffer_size=1 if profile is None else profile.controller.read_entries,
            write_buffer_size=1, priority_buffer_size=1,
            controller_plugins=plugins).to_config()
        if refresh:
            controller['refresh_manager'] = {'impl': 'W2WRWDLRefresh'}
            if profile is not None and profile.controller.refresh_phase=='staggered':
                controller['refresh_manager']['phase_cycles']=(channel%32)*profile.timing.nREFI//32
        controllers.append(controller)
    memory = ramulator.memory_system.GenericDRAM(
        clock_ratio=1, controllers=[],
        channel_mapper=ramulator.channel_mapper.PassThroughChannelMapper()).to_config()
    memory['controllers'] = controllers
    return dict(frontend=ramulator.frontend.External(clock_ratio=1).to_config(), memory_system=memory)


class RamulatorRWDL:
    tck_ps = 3760

    def __init__(self, memories, **kwargs):
        self.config = candidate_config(memories, **kwargs)
        bridge, path = load_bridge()
        self.impl = bridge.IncrementalMemory(self.config)
        self.bridge_sha256 = sha256(path.read_bytes()).hexdigest()
        self.accepted = self.completed = self.rejected = 0
        self.pending = set()
        self.memories = memories
        self.last_ps = 0

    def submit(self, channel, atom_address):
        if not 0 <= channel < self.memories*32 or not 0 <= atom_address < 1 << 20:
            raise ValueError('Out-of-range RWDL array address')
        ticket = self.accepted
        if not self.impl.send(ticket, channel, atom_address):
            self.rejected += 1
            return None
        self.accepted += 1
        self.pending.add(ticket)
        return ticket

    def advance(self, now):
        if now < self.last_ps:
            raise ValueError('Nonmonotonic RWDL time')
        self.last_ps = now
        result = self.impl.advance(now//self.tck_ps)
        for ticket, cycle in result:
            if ticket not in self.pending or cycle*self.tck_ps > now:
                raise RuntimeError('Invalid RWDL completion')
            self.pending.remove(ticket)
            self.completed += 1
        return result

    def record(self):
        def finite(value):
            if isinstance(value, dict): return {k: finite(v) for k,v in value.items()}
            if isinstance(value, list): return [finite(v) for v in value]
            if isinstance(value, float) and not math.isfinite(value): return None
            return value
        return dict(kind='ramulator_rwdl_candidate_v1', upstream_commit=UPSTREAM_COMMIT,
            bridge_sha256=self.bridge_sha256, config=self.config, config_sha256=digest(self.config),
            tck_ps=self.tck_ps, accepted_atoms=self.accepted, completed_atoms=self.completed,
            rejected_attempts=self.rejected, pending_atoms=len(self.pending),
            upstream_pending=self.impl.outstanding(), stats=finite(self.impl.stats()),
            scope='32 independent 128-Mbit arrays/M, published interface anchors, assumed array/refresh timing; uncalibrated')

    def close(self):
        self.impl.close()
