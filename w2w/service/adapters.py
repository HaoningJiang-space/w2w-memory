"""Legacy compatibility and the immutable Design -> solver adapter."""
from types import SimpleNamespace
import numpy as np
from w2w.domain import Geometry, Exposure, StaticLayout, MemoryFabricDesign
from w2w.endpoints.contracts import scalar_contract, role_envelope
from w2w.service.resources import build_fabric_ledger, route_resource_rows
from w2w.service.solver import FixedService
from w2w.constants import BANKS, BANK_BW


def EndpointFixedService(fabric, layout, contract='elastic', alpha=1., efficiency=1.):
    """Compatibility factory. Endpoint no longer subclasses the wafer solver."""
    outputs = [(('bank_output', m, b, p), fabric.limits[fabric.row['bank_output', m, b, p]], len(ports))
               for m in range(fabric.nm) for b, ports in enumerate(fabric.mask) for p in ports]
    routes = [((c, int(bank), edge), ('bank_output', int(bank) // BANKS, int(bank) % BANKS,
                                    fabric.edges[edge]['mp']))
              for c in range(fabric.nc) for bank in np.flatnonzero(layout.shares[c])
              for edge in fabric.paths.get((c, int(bank)), [])]
    envelope = scalar_contract(outputs, routes, fabric.nm, BANKS, BANK_BW, contract, alpha, efficiency)
    return FixedService(fabric, layout, envelope)


def freeze_design(name, structure, fabric, layout, endpoint, home_fraction):
    """Copy legacy mutable construction objects into immutable domain values."""
    from w2w.service.guaranteed_service_exchange import bank_coordinates
    p = fabric.physical
    r = p.memory[0]
    geometry = Geometry('H/plus', tuple((v.x, v.y) for v in p.compute),
                        tuple((v.x, v.y) for v in p.memory),
                        tuple((e['c'], e['m'], e['cp'], e['mp'], e['compute_port_fraction'],
                               e['memory_port_fraction']) for e in fabric.edges),
                        tuple(tuple(v) for v in bank_coordinates()),
                        tuple((v.x-r.x, v.y-r.y) for v in r.vertical_connectors))
    channels = fabric.channels
    exposure = Exposure(fabric.mask, channels.port_bits, channels.clock_ghz,
                        channels.controller_tb_s, pipeline_spacing_mm=channels.pipeline_spacing_mm)
    return MemoryFabricDesign(name, structure, geometry, exposure, endpoint,
                              StaticLayout(layout.shares), home_fraction)


class DesignFabric:
    """Narrow public design view used by the existing fixed-byte solver."""
    def __init__(self, design):
        g, x = design.geometry, design.exposure
        self.nc, self.nm = len(g.compute_xy), len(g.memory_xy)
        self.mask, self.nports, self.banks = x.mask, len(x.port_bits), len(x.mask)
        self.edges = [dict(c=c, m=m, cp=cp, mp=mp, compute_port_fraction=cf, memory_port_fraction=mf)
                      for c, m, cp, mp, cf, mf in g.routes]
        self.channels = SimpleNamespace(port_bits=x.port_bits, controller_tb_s=x.controller_tb_s,
                                        bank_link_bits=design.endpoint.word_bits,
                                        capacity=lambda w: w*x.clock_ghz/8000)
        ledger = build_fabric_ledger(self.nc, self.nm, x.mask, self.channels, self.edges,
                                    self.banks, x.bank_bw, bank_output_bw=x.bank_bw,
                                    include_controller=True)
        self.labels, self.limits, self.row = list(ledger.labels), ledger.capacities, ledger.row
        self.paths = {}
        for i, e in enumerate(self.edges):
            if self.limits[self.row['hb_edge', i]] > 0:
                for b, ports in enumerate(self.mask):
                    if e['mp'] in ports:
                        self.paths.setdefault((e['c'], e['m']*self.banks+b), []).append(i)

    def resources(self, bank, edge):
        return route_resource_rows(self.row, bank, dict(self.edges[edge], index=edge), self.banks)


def service_problem(design, envelope=None):
    fabric = DesignFabric(design)
    layout = SimpleNamespace(shares=np.array(design.layout.shares), sha256=design.layout.sha256)
    return FixedService(fabric, layout, role_envelope(design) if envelope is None else envelope)


def solve_service(design, workload, envelope=None, objective='throughput', minimum=0.):
    """Public immutable-design entrypoint; one LP implementation underneath."""
    return service_problem(design, envelope).solve(workload, minimum, objective)
