"""SeDRAM-inspired interface, with explicitly assumed array/refresh timings.

This is a new Ramulator standard, not an HBM2 preset with scaled bandwidth.
One channel contains one 128-Mbit array and an independent 128-bit RWDL.
"""
from ramulator.dram.spec import DRAMStandard, TimingConstraint as TC


class W2WRWDL(DRAMStandard):
    name = 'W2WRWDL'
    internal_prefetch_size = 1
    data_payload_bytes = 16
    read_latency = 'nCL + nBL'
    levels = dict(Channel='N_A', Rank='N_A', Bank='Closed', Row='Closed', Column='N_A')
    commands = ['ACT', 'PREpb', 'PREab', 'RD', 'WR', 'REFab']
    states = ['Opened', 'Closed', 'N_A']
    supported_requests = dict(Read='RD', Write='WR')
    timing_params = ['nBL', 'nCL', 'nRCD', 'nRP', 'nRAS', 'nRC', 'nWR',
                     'nRTP', 'nCWL', 'nWTR', 'nRTW', 'nRFC', 'nREFI', 'tCK_ps']
    org_presets = {'array128Mbit': dict(dq=128, channel_width=128, rank=1,
                                       bank=1, row=1 << 14, column=64)}
    # 3.76 ns interface and 6 ns CAS-to-data are public interface anchors.
    # CAS rounded up to 2 CK; callback includes one complete 16 B data beat.
    # All other values below are declared study assumptions, NOT SeDRAM bins.
    timing_presets = {'candidate3760ps': dict(nBL=1, nCL=2, nRCD=4, nRP=4,
        nRAS=9, nRC=13, nWR=4, nRTP=2, nCWL=2, nWTR=2, nRTW=2,
        nRFC=43, nREFI=1037, tCK_ps=3760)}
    timing_constraints = [
        TC('Channel', ['RD'], ['RD'], 'nBL'),
        TC('Channel', ['WR'], ['WR'], 'nBL'),
        TC('Channel', ['RD'], ['WR'], 'nCL + nBL + nRTW'),
        TC('Channel', ['WR'], ['RD'], 'nCWL + nBL + nWTR'),
        TC('Bank', ['ACT'], ['ACT'], 'nRC'),
        TC('Bank', ['ACT'], ['RD', 'WR'], 'nRCD'),
        TC('Bank', ['ACT'], ['PREpb', 'PREab'], 'nRAS'),
        TC('Bank', ['PREpb', 'PREab'], ['ACT'], 'nRP'),
        TC('Bank', ['RD'], ['PREpb', 'PREab'], 'nRTP'),
        TC('Bank', ['WR'], ['PREpb', 'PREab'], 'nCWL + nBL + nWR'),
        TC('Rank', ['ACT'], ['REFab'], 'nRC'),
        TC('Rank', ['PREpb', 'PREab'], ['REFab'], 'nRP'),
        TC('Rank', ['RD'], ['REFab'], 'nRTP + nRP'),
        TC('Rank', ['WR'], ['REFab'], 'nCWL + nBL + nWR + nRP'),
        TC('Rank', ['REFab'], ['ACT', 'PREpb', 'PREab', 'RD', 'WR', 'REFab'], 'nRFC'),
    ]


def generate(output):
    from pathlib import Path
    from ramulator.codegen import generate_header
    Path(output).write_text(generate_header(W2WRWDL))


if __name__ == '__main__':
    import sys
    generate(sys.argv[1])
