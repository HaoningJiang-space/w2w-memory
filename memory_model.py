"""Direct HB memory service bounds, not a DRAM timing or packet simulator.

Each repeated template has fixed total HB provisioning. A port's budget is
split by overlap area; adding neighbors does not create extra bandwidth.
Memory is an endpoint. No C-M-C forwarding or global address reachability.
"""
from dataclasses import dataclass, asdict
import math
import numpy as np
import networkx as nx
from scipy.optimize import linprog
from scipy.sparse import lil_matrix
from shapely.geometry import Polygon, box
from Reticle import create_reticle
from Wafer import Wafer, create_wafer
from System import System


def construct_memory_system(design, parameters):
    diameter = design['wafer_diameter']
    w, h = parameters['reticle_size']
    method = design['method']
    if method in ('aligned', 'half_shifted_x', 'half_shifted'):
        # Same C positions, C/M counts, areas and port templates in all three
        # designs. Reserve boundary space for a half shift in both dimensions.
        candidates = [(r*c, r, c) for r in range(1, int(diameter/h)+1)
                      for c in range(1, int(diameter/w)+1)
                      if ((c+1)*w/2)**2 + ((r+1)*h/2)**2 <= (diameter/2)**2]
        if not candidates:
            raise ValueError('Wafer too small for matched placement')
        _, rows, cols = max(candidates)
        shift = {'aligned': (0, 0), 'half_shifted_x': (w/2, 0),
                 'half_shifted': (w/2, h/2)}[method]
        wafers = []
        for typ, (dx, dy) in [('compute', (0, 0)), ('memory', shift)]:
            reticles = [create_reticle((c-(cols-1)/2)*w+dx,
                                      (r-(rows-1)/2)*h+dy,
                                      w, h, typ, 'rectangular', 0,
                                      'corners', (w/2, h/2))
                        for r in range(rows) for c in range(cols)]
            wafers.append(Wafer(reticles, diameter, typ, method))
    elif method == 'rotated':
        if tuple(parameters['reticle_size']) != (26.0, 33.0):
            raise ValueError('Upstream rotated template hardcodes 26 x 33 mm')
        utilization = design.get('wafer_utilization', 'rectangular')
        lower = create_wafer(None, diameter, 'compute', (w,h), 'compute',
                             utilization, 'rotated_lower', {})
        upper = create_wafer(lower, diameter, 'memory', (w,h), 'memory',
                             utilization, 'rotated_upper', {})
        wafers = [lower, upper]
    else:
        raise ValueError(f'Unsupported memory method: {method}')
    return System(wafers, 'memory_and_logic', diameter,
                  design.get('wafer_utilization', 'rectangular'), method,
                  'direct_only', 'analytical', 'synthetic_memory')


@dataclass(frozen=True)
class Budgets:
    # Illustrative decimal TB/s and GiB, not a calibrated DRAM product.
    compute_hb_tb_s: float = 4.0
    memory_hb_tb_s: float = 4.0
    controller_tb_s: float = 4.0
    dram_tb_s: float = 1.0
    capacity_gib: float = 16.0
    # Pooled service cap at one memory interface, as fraction of reticle BW.
    # 1.0 is optimistic all-bank access; 0.25 is a useful 4-port sensitivity.
    pool_port_fraction: float = 1.0

    def __post_init__(self):
        if not all(math.isfinite(v) and v > 0 for v in asdict(self).values()):
            raise ValueError('Budgets must be finite and positive')
        if self.pool_port_fraction > 1:
            raise ValueError('pool_port_fraction must not exceed one')


class MemoryFabric:
    def __init__(self, system, budgets=None, bank_mode='partitioned'):
        if bank_mode not in ('partitioned', 'pooled'):
            raise ValueError('bank_mode must be partitioned or pooled')
        if len(system.wafers) != 2:
            raise ValueError('Exactly two wafers are required')
        self.system, self.budgets, self.bank_mode = system, budgets or Budgets(), bank_mode
        self.compute, self.memory = (w.reticles for w in system.wafers)
        if not self.compute or not self.memory:
            raise ValueError('Both wafers must have reticles')
        if any(r.typ != 'compute' for r in self.compute) or any(r.typ != 'memory' for r in self.memory):
            raise ValueError('Expected compute wafer followed by memory wafer')
        self.memory_scale = np.array([r.get_area()/(26*33) for r in self.memory])
        self.edges = []
        self.validate_geometry()
        b = self.budgets
        for c, cr in enumerate(self.compute):
            for m, mr in enumerate(self.memory):
                for cp, cv in enumerate(cr.vertical_connectors):
                    for mp, mv in enumerate(mr.vertical_connectors):
                        # Same geometric rule as upstream, with area and tolerance.
                        area = self.region(cv).intersection(self.region(mv)).area
                        if area <= 1e-8:
                            continue
                        self.edges.append(dict(c=c, m=m, cp=cp, mp=mp,
                                               overlap_mm2=area,
                                               compute_port_fraction=area/(cv.w*cv.h),
                                               memory_port_fraction=area/(mv.w*mv.h)))

    def edge_bandwidth(self, e):
        return min(self.budgets.compute_hb_tb_s / len(self.compute[e['c']].vertical_connectors)
                   * e['compute_port_fraction'],
                   self.budgets.memory_hb_tb_s / len(self.memory[e['m']].vertical_connectors)
                   * e['memory_port_fraction'])

    @staticmethod
    def region(vc):
        return box(vc.x-vc.w/2, vc.y-vc.h/2, vc.x+vc.w/2, vc.y+vc.h/2)

    def validate_geometry(self):
        # Upstream disables several checks for roundoff. Here explicitly bound it.
        for wafer in self.system.wafers:
            polygons = [Polygon(r.shape_points) for r in wafer.reticles]
            for i, r in enumerate(wafer.reticles):
                if not r.is_in_wafer(wafer.diameter):
                    raise ValueError('Reticle outside wafer')
                for j in range(i):
                    if polygons[i].intersection(polygons[j]).area > 1e-6:
                        raise ValueError('Same-wafer reticle overlap')
                for vc in r.vertical_connectors:
                    if self.region(vc).difference(polygons[i]).area > 1e-6:
                        raise ValueError('Connector outside reticle')
                for p, vc in enumerate(r.vertical_connectors):
                    for other in r.vertical_connectors[:p]:
                        if self.region(vc).intersection(self.region(other)).area > 1e-6:
                            raise ValueError('Overlapping ports within reticle')
            # Repeated template: shape and connector locations relative to center.
            def signature(r):
                return ([(round(x-r.x,6),round(y-r.y,6)) for x,y in r.shape_points],
                        [(round(v.x-r.x,6),round(v.y-r.y,6),v.w,v.h) for v in r.vertical_connectors])
            if any(signature(r) != signature(wafer.reticles[0]) for r in wafer.reticles):
                raise ValueError('Nonidentical reticle templates within wafer')

    def summary(self):
        nc, nm = len(self.compute), len(self.memory)
        c_neighbors = [set() for _ in self.compute]
        m_neighbors = [set() for _ in self.memory]
        ports = [set() for _ in self.compute]
        chb, mhb = np.zeros(nc), np.zeros(nm)
        graph = nx.Graph()
        graph.add_nodes_from(range(nc+nm))
        for e in self.edges:
            c, m = e['c'], e['m']
            c_neighbors[c].add(m); m_neighbors[m].add(c)
            ports[c].add((m,e['mp']))
            chb[c] += self.edge_bandwidth(e); mhb[m] += self.edge_bandwidth(e)
            graph.add_edge(c,nc+m)
        capacity = []
        for c in range(nc):
            if self.bank_mode == 'pooled':
                scale = sum(self.memory_scale[m] for m in c_neighbors[c])
            else:
                scale = sum(self.memory_scale[m]/len(self.memory[m].vertical_connectors)
                            for m,p in ports[c])
            capacity.append(float(scale*self.budgets.capacity_gib))
        components = list(nx.connected_components(graph))
        distances = [d for node, ds in nx.all_pairs_shortest_path_length(graph)
                     for dest,d in ds.items() if dest != node]
        return dict(method=self.system.method, n_compute=nc, n_memory=nm,
                    compute_degree=[len(s) for s in c_neighbors],
                    memory_degree=[len(s) for s in m_neighbors],
                    reachable_capacity_gib=capacity,
                    total_physical_capacity_gib=float(sum(self.memory_scale)*self.budgets.capacity_gib),
                    compute_hb_tb_s=chb.tolist(), memory_hb_tb_s=mhb.tolist(),
                    component_count=len(components),
                    structural_diameter=nx.diameter(graph) if len(components)==1 else None,
                    structural_max_finite_distance=max(distances,default=0),
                    structural_mean_finite_distance=float(np.mean(distances)) if distances else None,
                    direct_access_distance=1 if self.edges else None,
                    forwarding_supported=False, bank_mode=self.bank_mode,
                    compute_area_mm2=sum(r.get_area() for r in self.compute),
                    memory_area_mm2=sum(r.get_area() for r in self.memory),
                    budgets=asdict(self.budgets),
                    edges=[dict(e, hb_tb_s=self.edge_bandwidth(e)) for e in self.edges])

    def solve(self, demand, objective='throughput', allowed_memories=None):
        """Fluid service bound with freely placeable data unless affinity supplied.

        throughput maximizes sum(x_e); fair maximizes a common completion-rate
        multiplier alpha for positive demands. Static affinity can forbid edges.
        This does not allocate data capacity or model migration/refresh/row hits.
        """
        demand = np.asarray(demand, dtype=float)
        nc, nm = len(self.compute), len(self.memory)
        if demand.shape != (nc,) or not np.isfinite(demand).all() or (demand < 0).any():
            raise ValueError('Demand must contain one finite nonnegative rate per compute')
        if objective not in ('throughput', 'fair'):
            raise ValueError('Unknown objective')
        if allowed_memories is not None and len(allowed_memories) != nc:
            raise ValueError('Affinity must have one set per compute')
        es = [e for e in self.edges if allowed_memories is None or e['m'] in allowed_memories[e['c']]]
        if not es or not demand.any():
            return dict(total_tb_s=0.0, served_tb_s=[0.0]*nc, common_fraction=0.0,
                        max_constraint_violation=0.0)
        b = self.budgets
        groups = {}
        def group(key, limit, index):
            if key not in groups:
                groups[key] = (limit, [])
            groups[key][1].append(index)
        for i,e in enumerate(es):
            c,m,cp,mp = e['c'],e['m'],e['cp'],e['mp']
            group(('compute',c), min(demand[c],b.controller_tb_s), i)
            group(('memory',m), b.dram_tb_s*self.memory_scale[m], i)
            group(('chb',c,cp), b.compute_hb_tb_s/len(self.compute[c].vertical_connectors), i)
            group(('mhb',m,mp), b.memory_hb_tb_s/len(self.memory[m].vertical_connectors), i)
            fraction = (1/len(self.memory[m].vertical_connectors) if self.bank_mode=='partitioned'
                        else b.pool_port_fraction)
            group(('bankport',m,mp), b.dram_tb_s*self.memory_scale[m]*fraction, i)
        fair = objective == 'fair'
        active = np.flatnonzero(demand > 0)
        a = lil_matrix((len(groups)+(len(active) if fair else 0),len(es)+int(fair)))
        rhs=[]
        for row,(limit,indices) in enumerate(groups.values()):
            a[row,indices]=1; rhs.append(limit)
        if fair:
            for row,c in enumerate(active,start=len(groups)):
                a[row,[i for i,e in enumerate(es) if e['c']==c]]=-1
                a[row,-1]=demand[c]; rhs.append(0)
        costs = np.zeros(a.shape[1]) if fair else -np.ones(len(es))
        if fair: costs[-1]=-1
        bounds=[(0,self.edge_bandwidth(e)) for e in es]+([(0,1)] if fair else [])
        res=linprog(costs,A_ub=a.tocsr(),b_ub=rhs,bounds=bounds,method='highs')
        if not res.success:
            raise RuntimeError(res.message)
        served=np.zeros(nc)
        for e,x in zip(es,res.x[:len(es)]): served[e['c']]+=x
        residual=float(max(0,np.max(a@res.x-np.asarray(rhs))))
        if residual>1e-7: raise RuntimeError('LP constraint violation')
        return dict(total_tb_s=float(served.sum()),served_tb_s=served.tolist(),
                    common_fraction=float(res.x[-1]) if fair else float(min(served[active]/demand[active])),
                    max_constraint_violation=residual)
