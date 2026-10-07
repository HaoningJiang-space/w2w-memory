"""Compose endpoint reservations through the public immutable-design service API."""
from functools import lru_cache
from itertools import product
from math import comb
import numpy as np
from w2w.endpoints.role_execution import execute_periodic, ratio_sequence
from w2w.service.adapters import service_problem


@lru_cache(None)
def local_trace(spec, sequence, profile):
    return execute_periodic(spec, sequence, profile)


class CandidateEvaluator:
    def __init__(self, candidate):
        self.candidate = candidate
        self.profile = candidate.endpoint.native
        self.model = service_problem(candidate)
        self.f = self.model.source_fabric
        self.layout = self.model.layout
        self.spec = candidate.endpoint
        self.nb = len(candidate.exposure.mask)
        self.bank_bw = candidate.exposure.bank_bw
        self.owners = {bank: tuple(int(c) for c in np.flatnonzero(self.layout.shares[:, bank]))
                       for bank in range(self.f.nm * self.nb)}
        self.ports = {(c, bank): self.f.edges[self.f.paths[c, bank][0]]['mp']
                      for bank, owners in self.owners.items() for c in owners}
        self.sequences = {}
        fraction = candidate.home_fraction
        for bank, owners in self.owners.items():
            m = bank // self.nb
            if owners == (m,):
                sequence = (0,)
            else:
                if m not in owners or len(owners) != 2:
                    raise ValueError('Unsupported ownership pattern')
                peer = next(c for c in owners if c != m)
                sequence = ratio_sequence(0, self.ports[peer, bank], fraction.numerator, fraction.denominator)
            self.sequences[bank] = sequence
        self.composition = self._composition_certificate()

    def _composition_certificate(self):
        # Simultaneous drains may exceed native issue rate transiently. Aggregate
        # only downstream resources; native issue is separately checked per slot.
        peaks = np.zeros(len(self.f.limits))
        controller = np.zeros(self.f.nc)
        for bank, owners in self.owners.items():
            for c in owners:
                edge = self.f.paths[c, bank][0]
                peak = self.spec.widths[self.ports[c, bank]] / self.spec.word_bits * self.bank_bw
                for row in self.f.resources(bank, edge)[2:]:
                    peaks[row] += peak
                controller[c] += peak
        overflow = max(float(np.max(peaks - self.f.limits)),
                       float(np.max(controller - self.f.channels.controller_tb_s)), 0.)
        if overflow > 1e-10:
            raise ValueError('Instantaneous downstream composition requires joint credits')
        return dict(verified=True, maximum_overflow_tb_s=overflow,
                    maximum_controller_peak_tb_s=float(max(controller)),
                    maximum_downstream_utilization=float(np.max(peaks / np.maximum(self.f.limits, 1e-30))),
                    method='Sum all resident output width peaks at each HB/memory/compute port and controller; no link latency simulation')

    def bank_rates(self, bank, active):
        users = tuple(c for c in self.owners[bank] if c in active)
        if not users:
            return {}
        ports = {self.ports[c, bank] for c in users}
        sequence = tuple(p for p in self.sequences[bank] if p in ports)
        trace = local_trace(self.spec, sequence, self.profile)
        return {c: trace['rate_per_native'][self.ports[c, bank]] * self.bank_bw for c in users}

    def achieved_rates(self, active):
        active = set(active)
        rates = np.full(self.f.nc, np.inf)
        caps = {}
        for bank in self.owners:
            for c, cap in self.bank_rates(bank, active).items():
                caps[c, bank] = cap
                rates[c] = min(rates[c], cap / self.layout.shares[c, bank])
        rates[[c for c in range(self.f.nc) if c not in active]] = 0.
        if not np.isfinite(rates).all():
            raise ValueError('An active request has no data service')
        return rates, caps

    def replay(self, active):
        rates, caps = self.achieved_rates(active)
        demand = np.zeros(self.f.nc)
        demand[list(active)] = 4.
        replay = self.model.with_delivered_caps(caps)
        solved = replay.solve(demand, minimum=0)
        common = replay.solve(demand, minimum=0, objective='common')
        upper = self.model.solve(demand, minimum=0)
        residual = replay.audit_rates(rates)
        if residual > 1e-8 or not np.allclose(rates, solved['served_tb_s'], atol=1e-8):
            raise RuntimeError('Execution witness and full-byte resource LP disagree')
        if not np.isclose(min(rates[list(active)]), 4 * common['common_fraction'], atol=1e-8):
            raise RuntimeError('Common completion disagrees with achieved reservation rates')
        return dict(active=list(active), served_tb_s=rates.tolist(),
                    executed_tb_s=solved['tb_s_per_active'], common_tb_s=4 * common['common_fraction'],
                    fluid_upper_tb_s=upper['tb_s_per_active'],
                    floor_one_feasible=bool(min(rates[list(active)]) >= 1 - 1e-9),
                    witness_residual=residual, lp_residual=solved['constraint_residual'],
                    lp_solves=3)

    def population(self, k=9):
        """Exact marginal expectation over uniform fixed-cardinality activity.

        Each client depends only on the owners of its own banks. All such local
        events are counted with hypergeometric probabilities, including boundary
        private banks. Correlated events between clients do not affect the mean.
        """
        n = self.f.nc
        if not 1 <= k <= n:
            raise ValueError('Invalid activity cardinality')
        clients = []
        for c in range(n):
            banks = np.flatnonzero(self.layout.shares[c])
            neighbors = sorted({v for bank in banks for v in self.owners[int(bank)] if v != c})
            events = []
            for flags in product((0, 1), repeat=len(neighbors)):
                remaining = k - 1 - sum(flags)
                outsiders = n - 1 - len(neighbors)
                probability = comb(outsiders, remaining) / comb(n - 1, k - 1) if 0 <= remaining <= outsiders else 0.
                active = {c} | {v for v, flag in zip(neighbors, flags) if flag}
                rate = min(self.bank_rates(int(bank), active)[c] / self.layout.shares[c, bank] for bank in banks)
                events.append(dict(neighbor_active=list(flags), probability=probability, rate=rate))
            if abs(sum(v['probability'] for v in events) - 1) > 1e-12:
                raise RuntimeError('Activity probabilities do not sum to one')
            clients.append(dict(client=c, neighbors=neighbors, events=events,
                                mean=sum(v['probability'] * v['rate'] for v in events)))
        return dict(active_count=k, exact_mean_tb_s=float(np.mean([v['mean'] for v in clients])),
                    clients=clients, scope='Exact activity expectation of registered periodic reservations; not an optimized universal capacity region')

    def traces(self):
        keys = set()
        for bank, owners in self.owners.items():
            for flags in product((0, 1), repeat=len(owners)):
                ports = {self.ports[c, bank] for c, flag in zip(owners, flags) if flag}
                sequence = tuple(p for p in self.sequences[bank] if p in ports)
                if sequence:
                    keys.add(sequence)
        return [local_trace(self.spec, key, self.profile) for key in sorted(keys)]
