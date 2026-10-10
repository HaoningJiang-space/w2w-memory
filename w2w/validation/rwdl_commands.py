"""Offline read-only RWDL command/address audit, independent of Ramulator codegen.

This checks the declared candidate timing, not measured SeDRAM timing. Writes are
deliberately rejected: a read probe cannot establish write-path correctness.
"""
import csv
from collections import Counter


def expected_atoms(result):
    """Reconstruct physical atoms directly from logical read ranges."""
    objects={o['id']:o for o in result['graph']['objects']}
    memories={m['id']:m for m in result['spec']['memories']}
    domains=list(result['spec']['stack']['dram_domains'])
    channel={d['id']:i for i,d in enumerate(domains)}
    addresses=Counter()
    for task in result['graph']['tasks']:
        for access in task['reads']:
            obj=objects[access['object_id']];memory=memories[obj['memory']]
            begin=obj['offset_bytes']+access['offset_bytes']
            end=begin+access['size_bytes']
            for byte in range(begin,end,16):
                word,half=divmod(byte,32);bank=word%memory['banks']
                domain=memory['domain_ids'][bank];atom=2*(word//memory['banks'])+half//16
                addresses[channel[domain],atom]+=1
    return addresses


def audit_channel(rows, policy, channel, capacity_bytes):
    # One rank and one bank per independent domain. These explicit constraints
    # correspond to the declared read-only standard, without importing its
    # TimingConstraint objects or scheduler implementation.
    p=policy
    pre=('PREpb','PREab')
    constraints=[(('RD',),('RD',),p['nBL']),
        (('ACT',),('ACT',),p['nRC']),
        (('ACT',),('RD',),p['nRCD']),
        (('ACT',),pre,p['nRAS']),
        (pre,('ACT',),p['nRP']),
        (('RD',),pre,p['nRTP']),
        (('ACT',),('REFab',),p['nRC']),
        (pre,('REFab',),p['nRP']),
        (('RD',),('REFab',),p['nRTP']+p['nRP']),
        (('REFab',),('ACT','PREpb','PREab','RD','REFab'),p['nRFC'])]
    last={};open_row=None;clock=-1;addresses=Counter();counts=Counter()
    first_rd=last_rd=None
    for row in rows:
        at=int(row['clock']);cmd=row['command']
        if cmd not in ('ACT','PREpb','PREab','RD','REFab'):
            raise ValueError('Unsupported command in read-only RWDL probe')
        if at<=clock:raise ValueError('More than one command/domain/cycle or nonmonotonic trace')
        clock=at
        # All data commands must refer to this controller's one physical bank.
        if cmd in ('ACT','RD') and (int(row['Channel'])!=channel or int(row['Rank'])!=0 or int(row['Bank'])!=0):
            raise ValueError('Command escaped its physical domain')
        for earlier,later,gap in constraints:
            if cmd in later and any(at-last[x]<gap for x in earlier if x in last):
                raise ValueError(f'RWDL command timing violation: {earlier}->{cmd}')
        if cmd=='ACT':
            selected=int(row['Row'])
            if open_row is not None or not 0<=selected<capacity_bytes//1024:
                raise ValueError('ACT on an open bank or outside declared array')
            open_row=selected
        elif cmd=='RD':
            column=int(row['Column'])
            if open_row is None or int(row['Row'])!=open_row or not 0<=column<64:
                raise ValueError('RD without the matching open row/column')
            addresses[channel,open_row*64+column]+=1
            if first_rd is None:first_rd=at
            last_rd=at
        elif cmd in pre:open_row=None
        elif open_row is not None:raise ValueError('Refresh issued without closing the array')
        last[cmd]=at;counts[cmd]+=1
    return addresses,dict(commands=dict(counts),first_rd_cycle=first_rd,last_rd_cycle=last_rd,
        read_bus_cycles=counts['RD']*p['nBL'],refresh_busy_cycles=counts['REFab']*p['nRFC'])


def audit_rwdl_commands(result, trace_base):
    from pathlib import Path
    base=Path(trace_base);stack=result['spec']['stack'];expected=expected_atoms(result)
    observed=Counter();channels={}
    for i,domain in enumerate(stack['dram_domains']):
        path=Path(str(base)+f'.ch{i}')
        with path.open() as file:
            reader=csv.DictReader(file)
            if reader.fieldnames!=['clock','command','Channel','Rank','Bank','Row','Column','type','source']:
                raise ValueError('Unsupported native command trace schema')
            atoms,record=audit_channel(reader,stack['native_policy'],i,domain['capacity_bytes'])
        observed.update(atoms);channels[domain['id']]=record
    if expected!=observed:raise ValueError('Native RD address multiset differs from the required physical reads')
    if result['native']['completed_atoms']!=sum(observed.values()):
        raise ValueError('Native callbacks differ from actual RD commands')
    return dict(passed=True,read_atoms=sum(observed.values()),active_read_domains=sum(bool(r['commands'].get('RD')) for r in channels.values()),
        channels=channels,contract='one command/domain/cycle; open-row legality, declared ACT/PRE/RD/REF gaps and exact physical RD address multiset',
        limits='read-only candidate command audit; no WR path, silicon calibration, power or temperature validation')
