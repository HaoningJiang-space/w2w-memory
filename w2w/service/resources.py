"""Canonical bank/path resource rows and their load/residual operations."""
from dataclasses import dataclass
import numpy as np
from scipy.sparse import coo_matrix, vstack
from w2w.constants import BANKS, BANK_BW


@dataclass
class ResourceLedger:
    labels: tuple
    capacities: np.ndarray
    matrix: object = None

    @property
    def row(self):
        return {label: i for i, label in enumerate(self.labels)}

    def load(self, witness):
        if self.matrix is None:
            raise ValueError('Resource ledger has no bound route variables')
        return self.matrix @ witness

    def residual(self, witness):
        return max(0., float(np.max(self.load(witness) - self.capacities)))


def build_fabric_ledger(nc, nm, mask, channels, edges, banks=BANKS, bank_bw=BANK_BW,
                        bank_output_bw=None, include_controller=False):
    """One definition shared by legacy ExposureFabric and immutable designs."""
    labels, capacities = [], []
    def add(label, capacity):
        labels.append(label)
        capacities.append(capacity)
    for m in range(nm):
        for b, ports in enumerate(mask):
            add(('bank', m, b), bank_bw)
            for p in ports:
                add(('bank_output', m, b, p), channels.capacity(channels.bank_link_bits)
                    if bank_output_bw is None else bank_output_bw)
        for p, width in enumerate(channels.port_bits):
            add(('memory_group_arb', m, p), channels.capacity(width))
    for c in range(nc):
        for p, width in enumerate(channels.port_bits):
            add(('compute_port', c, p), channels.capacity(width))
    for i, e in enumerate(edges):
        add(('hb_edge', i), min(channels.capacity(channels.port_bits[e['cp']]) * e['compute_port_fraction'],
                              channels.capacity(channels.port_bits[e['mp']]) * e['memory_port_fraction']))
    if include_controller:
        for c in range(nc):
            add(('controller', c), channels.controller_tb_s)
    return ResourceLedger(tuple(labels), np.array(capacities))


def route_resource_rows(row, bank, edge, banks=BANKS):
    m, b = divmod(bank, banks)
    return [row['bank', m, b], row['bank_output', m, b, edge['mp']],
            row['memory_group_arb', m, edge['mp']], row['compute_port', edge['c'], edge['cp']],
            row['hb_edge', edge['index']]]


def bind_resource_ledger(fabric, routes, nvar, envelope=None):
    """Bind physical and endpoint capacities to the same route variables."""
    labels = list(fabric.labels)
    caps = fabric.limits.copy()
    row = fabric.row
    rr, cc, vv = [], [], []
    route_columns = {}
    for col, c, bank, edge in routes:
        ids = fabric.resources(bank, edge)
        rr.extend(ids)
        cc.extend([col] * len(ids))
        vv.extend([1.] * len(ids))
        route_columns[c, bank, edge] = col
    for c in range(fabric.nc):
        if ('controller', c) in row:
            rr.append(row['controller', c])
            cc.append(c)
            vv.append(1.)
    matrix = coo_matrix((vv, (rr, cc)), shape=(len(caps), nvar)).tocsr()
    if envelope is not None:
        for label, capacity in envelope.resource_caps:
            if label not in row:
                raise ValueError('Endpoint envelope names an absent resource')
            caps[row[label]] = min(caps[row[label]], capacity)
        extra_rr, extra_cc, extra_vv, extra_caps, extra_labels = [], [], [], [], []
        def add(label, terms, capacity):
            idx = len(extra_caps)
            if label in row or label in extra_labels:
                raise ValueError('Duplicate resource label')
            for key, coefficient in terms:
                if key not in route_columns:
                    raise ValueError('Envelope names an absent physical route')
                extra_rr.append(idx)
                extra_cc.append(route_columns[key])
                extra_vv.append(coefficient)
            extra_caps.append(capacity)
            extra_labels.append(label)
        for limit in envelope.limits:
            add(limit.label, limit.terms, limit.capacity)
        if envelope.restrict_paths:
            path_caps = dict(envelope.path_caps)
            known = {(c, bank) for _, c, bank, _ in routes}
            if set(path_caps) - known:
                raise ValueError('Delivered caps name an absent resident path')
            for col, c, bank, edge in routes:
                if len(fabric.paths[c, bank]) != 1:
                    raise ValueError('Replay requires unique route')
                add(('executed_route', c, bank), (((c, bank, edge), 1.),), path_caps.get((c, bank), 0.))
        if extra_caps:
            extra = coo_matrix((extra_vv, (extra_rr, extra_cc)), shape=(len(extra_caps), nvar)).tocsr()
            matrix = vstack([matrix, extra], format='csr')
            caps = np.r_[caps, extra_caps]
            labels.extend(extra_labels)
    return ResourceLedger(tuple(labels), caps, matrix)
