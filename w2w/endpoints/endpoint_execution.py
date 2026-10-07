"""Complete-word endpoint execution and a bridge to the existing fixed-byte LP.

This is a specified digital microarchitecture, not a calibrated DRAM timing model.
One native slot admits at most one word. Outputs drain bits independently. A
queue slot includes the word currently in the serializer; depth zero explicitly
uses the blocking direct path, with one shared holding register.
"""
from collections import deque
from copy import copy
import numpy as np
from scipy.sparse import coo_matrix, vstack
from w2w.constants import BANKS,BANK_BW
from w2w.service.guaranteed_service_exchange import FixedService


def execute(output_bits=128, depth=1, active=(0, 1), mode='buffered',
            policy='round_robin', burst=8, slots=8192, warmup=1024,
            word_bits=256, stall_period=0, stall_length=0):
    """Saturated fixed byte classes, two destinations; count only complete words.

    ordered preserves the repeated destination sequence 0^burst,1^burst.
    round_robin may bypass a full destination, but never changes a word's owner.
    Issue occurs before drain each slot. No mid-slot issue or clock-rate packing.
    Warmup traffic remains in queues and is not discarded at measurement start.
    """
    if mode not in ('direct', 'buffered') or policy not in ('round_robin', 'ordered'):
        raise ValueError('Unknown implementation or arbitration')
    if not active or len(set(active)) != len(active) or any(e not in (0, 1) for e in active):
        raise ValueError('One or two distinct output IDs required')
    if any(int(v) != v or v < 0 for v in (depth, warmup, stall_period, stall_length)):
        raise ValueError('Nonnegative integer parameters required')
    if not 0 < output_bits <= word_bits or slots <= 0 or burst <= 0:
        raise ValueError('Invalid width or duration')
    blocking = mode == 'direct' or depth == 0
    capacity = 1 if blocking else depth
    queues = [deque(), deque()]
    sequence = [e for e in active for _ in range(burst)]
    cursor = 0; issued = completed = sent_bits = 0
    counts = [0, 0]; peaks = [0, 0]; backpressure = 0
    before = [0, 0]; done = [0, 0]; max_latency = 0
    last_tag = [-1, -1]
    for tick in range(warmup + slots):
        if tick == warmup: before = counts.copy()
        def room(e):
            return not any(queues) if blocking else len(queues[e]) < capacity
        chosen = None
        if policy == 'ordered':
            e = sequence[cursor % len(sequence)]
            if room(e): chosen = e; cursor += 1
        else:
            for offset in range(len(active)):
                e = active[(cursor + offset) % len(active)]
                if room(e):
                    chosen = e; cursor = (cursor + offset + 1) % len(active); break
        if chosen is not None:
            # A tag is an immutable unique complete-word/address transaction.
            queues[chosen].append([issued, word_bits, tick]); issued += 1
        elif tick >= warmup: backpressure += 1
        for e in (0, 1): peaks[e] = max(peaks[e], len(queues[e]))
        for e in (0, 1):
            budget = output_bits
            if stall_period and tick % stall_period < stall_length: budget = 0
            while budget and queues[e]:
                item = queues[e][0]; amount = min(budget, item[1])
                item[1] -= amount; budget -= amount; sent_bits += amount
                if item[1] == 0:
                    tag, _, arrival = queues[e].popleft()
                    assert tag > last_tag[e]; last_tag[e] = tag
                    completed += 1; counts[e] += 1
                    if tick >= warmup: max_latency = max(max_latency, tick - arrival + 1)
        # Native service, bounded storage and complete-word conservation.
        assert issued <= tick + 1
        assert all(len(q) <= capacity for q in queues)
        assert not blocking or sum(map(len, queues)) <= 1
        assert issued == completed + sum(map(len, queues))
        assert issued * word_bits == sent_bits + sum(v[1] for q in queues for v in q)
    done = [counts[e] - before[e] for e in (0, 1)]
    return dict(output_bits=output_bits, word_bits=word_bits, alpha=output_bits/word_bits,
        depth=depth, mode=mode, effective_mode='direct' if blocking else 'buffered',
        policy=policy, burst=burst, active=list(active), slots=slots, warmup=warmup,
        delivered_words=done, rate_per_native=[v/slots for v in done],
        total_per_native=sum(done)/slots, peak_words=peaks,
        backpressure_slots=backpressure, max_latency_slots=max_latency,
        issued_words=issued, completed_words=completed,
        outstanding_words=sum(map(len, queues)), conservation_checked_every_slot=True,
        storage_bits=(word_bits if blocking else 2*depth*word_bits))


class EndpointFixedService(FixedService):
    """Reuse FixedService byte equalities; add actual shared-path time rows.

    All addresses of a modeled bank are accessible through its declared mask.
    That is a complete digital-export assumption, not an arbitrary LIO tap claim.
    Buffered is a fluid upper envelope; finite-depth execution is separate.
    """
    def __init__(self, fabric, layout, contract='elastic', alpha=1., efficiency=1.):
        if contract not in ('elastic', 'fixed_share', 'direct', 'buffered_envelope'):
            raise ValueError('Unknown endpoint contract')
        if not 0 < alpha <= 1 or not 0 < efficiency <= 1: raise ValueError('Invalid contract')
        super().__init__(fabric, layout)
        self.fabric = copy(fabric)
        self.fabric.labels = list(fabric.labels); self.fabric.row = dict(fabric.row)
        self.fabric.limits = fabric.limits.copy()
        self.contract = contract; self.alpha = alpha
        for m in range(fabric.nm):
            for b, ports in enumerate(fabric.mask):
                cap = min(alpha,1/len(ports))*BANK_BW if contract == 'fixed_share' else alpha*BANK_BW
                for p in ports:
                    row = fabric.row['bank_output', m, b, p]
                    self.fabric.limits[row] = min(self.fabric.limits[row], cap)
        self.route_variables = []
        col = fabric.nc
        for c in range(fabric.nc):
            for bank in np.flatnonzero(layout.shares[c]):
                for edge in fabric.paths.get((c, int(bank)), []):
                    self.route_variables.append((col, c, int(bank), edge)); col += 1
        assert col == self.nvar
        if contract in ('direct', 'buffered_envelope'):
            rr=[]; cc=[]; vv=[]
            for col, c, bank, edge in self.route_variables:
                m, b = divmod(bank, BANKS)
                peak = self.fabric.limits[fabric.row['bank_output', m, b, fabric.edges[edge]['mp']]]
                rr.append(bank); cc.append(col)
                vv.append(1/peak if contract == 'direct' else 1/BANK_BW)
            extra=coo_matrix((vv,(rr,cc)),shape=(fabric.nm*BANKS,self.nvar)).tocsr()
            self._append(extra, np.full(fabric.nm*BANKS,efficiency),
                         [('endpoint_time',m,b) for m in range(fabric.nm) for b in range(BANKS)])

    def _append(self, matrix, limits, labels):
        offset=len(self.fabric.limits)
        self.ub=vstack([self.ub,matrix],format='csr')
        self.fabric.limits=np.r_[self.fabric.limits,limits]
        self.fabric.labels.extend(labels)
        self.fabric.row.update({label:offset+i for i,label in enumerate(labels)})

    def with_delivered_caps(self, caps):
        """Scenario-specific achieved schedule caps, NOT a universal contract.

        caps[(c,bank)] is measured complete-word service. Routes must be unique;
        the caller verifies physical port usage and fixed-layout consistency.
        """
        out=copy(self);out.fabric=copy(self.fabric)
        out.fabric.labels=list(self.fabric.labels);out.fabric.row=dict(self.fabric.row)
        rr=[];cc=[];vv=[];limits=[];labels=[]
        for col,c,bank,edge in self.route_variables:
            if len(self.fabric.paths[c,bank]) != 1: raise ValueError('Replay requires unique route')
            rr.append(len(limits));cc.append(col);vv.append(1.)
            limits.append(caps.get((c,bank),0.));labels.append(('executed_route',c,bank))
        extra=coo_matrix((vv,(rr,cc)),shape=(len(limits),self.nvar)).tocsr()
        out._append(extra,limits,labels)
        return out
