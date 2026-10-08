"""Audit fixed-direction reuse at the region/bank-point abstraction boundary.

No performance search, no claim that a stepper can rotate individual exposures,
no pad-level equivalence and no inferred PPA for an adapted binding network.
"""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess

import networkx as nx
import numpy as np
from scipy.optimize import linprog
from shapely.affinity import rotate, translate
from shapely.geometry import Polygon

from w2w.service.guaranteed_service_exchange import contoured_geometry
from w2w.synthesis.provisioning_catalog import candidate_designs

ROOT = Path(__file__).resolve().parents[2]


def point_permutation(points, degrees, tolerance=1e-7):
    """Old physical point -> coincident canonical point, or None."""
    angle = np.deg2rad(degrees)
    transform = np.array([[np.cos(angle), -np.sin(angle)],
                          [np.sin(angle), np.cos(angle)]])
    points = np.asarray(points)
    distances = np.max(np.abs((points @ transform.T)[:, None] - points[None]), axis=2)
    matches = distances <= tolerance
    if not np.all(matches.sum(axis=0) == 1) or not np.all(matches.sum(axis=1) == 1):
        return None
    return np.argmax(matches, axis=1).tolist()


def balanced_support(n, edges):
    """Independent combinatorial/continuous certificates for unit C/M balance.

    This drops all endpoint/HB caps: infeasibility of off-home use here also
    rules it out in a tighter model, only under the stated unit full-load floor.
    """
    edges = sorted(set(edges))
    graph = nx.Graph()
    left = [('c', i) for i in range(n)]
    right = [('m', i) for i in range(n)]
    graph.add_nodes_from(left + right)
    graph.add_edges_from((('c', c), ('m', m)) for c, m in edges)
    usable = []
    for c, m in edges:
        reduced = graph.copy()
        reduced.remove_nodes_from([('c', c), ('m', m)])
        matching = nx.bipartite.maximum_matching(reduced, top_nodes=set(left) - {('c', c)})
        if len(matching) == 2 * (n - 1):
            usable.append([c, m])
    matrix = np.zeros((2 * n, len(edges)))
    for j, (c, m) in enumerate(edges):
        matrix[c, j] = matrix[n + m, j] = 1
    objective = -np.array([float(c != m) for c, m in edges])
    solved = linprog(objective, A_eq=matrix, b_eq=np.ones(2 * n), bounds=(0, None), method='highs')
    if not solved.success:
        raise ValueError('No balanced layout exists even in the relaxed graph')
    residual = float(np.max(np.abs(matrix @ solved.x - 1)))
    if residual > 1e-8:
        raise ValueError('Invalid LP certificate')
    return dict(edges=len(edges), matching_usable_edges=usable,
                maximum_total_nonhome_fraction=max(0., float(-solved.fun)),
                equality_residual=residual,
                lp_scope='Unit row/column sums; endpoint/HB caps relaxed; no routing or replication')


def audit():
    physical = contoured_geometry()
    design = candidate_designs()[0]['b_cfg']
    geometry = design.geometry
    r = physical.memory[0]
    contour = translate(Polygon(r.shape_points), -r.x, -r.y)
    regions = [translate(physical.region(v), -r.x, -r.y) for v in r.vertical_connectors]
    symmetry = []
    for degrees in (0, 90, 180, 270):
        banks = point_permutation(geometry.bank_xy, degrees)
        ports = point_permutation(geometry.port_xy, degrees)
        contour_error = rotate(contour, degrees, origin=(0, 0)).symmetric_difference(contour).area
        port_error = (max(rotate(region, degrees, origin=(0, 0)).symmetric_difference(regions[ports[p]]).area
                          for p, region in enumerate(regions)) if ports is not None else None)
        symmetry.append(dict(degrees=degrees, bank_permutation=banks, port_permutation=ports,
                             contour_difference_mm2=contour_error, port_difference_mm2=port_error,
                             region_and_bank_point_symmetry=banks is not None and ports is not None
                             and contour_error < 1e-7 and port_error < 1e-7))
    nb = len(geometry.bank_xy)
    required = []
    for c, row in enumerate(design.layout.shares):
        for bank, fraction in enumerate(row):
            if not fraction:
                continue
            m, b = divmod(bank, nb)
            paths = [e for e in geometry.routes if e[0] == c and e[1] == m
                     and e[3] in design.exposure.mask[b]]
            if len(paths) != 1:
                raise ValueError('Frozen byte does not have a unique route')
            required.append((c, m, b, paths[0][3], fraction))
    uniform = []
    for p in range(1, len(geometry.port_xy)):
        missing = [v for v in required if v[3] not in (0, p)]
        edges = [(e[0], e[1]) for e in geometry.routes if e[3] in (0, p)]
        cert = balanced_support(len(geometry.compute_xy), edges)
        uniform.append(dict(shared_port=p, missing_frozen_bank_dependencies=len(missing),
                            affected_compute=sorted({v[0] for v in missing}),
                            missing_fraction_by_compute={str(c):sum(v[4] for v in missing if v[0] == c)
                                                        for c in sorted({v[0] for v in missing})},
                            balanced_layout_relaxation=cert))
    for s in symmetry:
        if s['region_and_bank_point_symmetry']:
            permutation = s['port_permutation']
            for values in (design.endpoint.widths, design.endpoint.depths, design.exposure.port_bits):
                if any(values[p] != values[q] for p, q in enumerate(permutation)):
                    raise ValueError('Geometric symmetry does not preserve provisioned widths/depths')
    orientation = []
    for m, wanted in enumerate(design.shared_directions):
        choices = [s for s in symmetry if s['region_and_bank_point_symmetry']
                   and s['port_permutation'][2] == wanted and s['port_permutation'][0] == 0]
        if not choices:
            raise ValueError('No regional orientation realizes the frozen shared port')
        orientation.append(dict(memory=m, degrees=choices[0]['degrees'], selected_port=wanted))
    # Reconstruct overlap from rotated rectangles, rather than renaming ports.
    rebuilt = []
    for instance in orientation:
        m, degrees = instance['memory'], instance['degrees']
        s = next(s for s in symmetry if s['degrees'] == degrees)
        mr = physical.memory[m]
        for local_port, local_region in enumerate(regions):
            world = translate(rotate(local_region, degrees, origin=(0, 0)), mr.x, mr.y)
            for c, cr in enumerate(physical.compute):
                for cp, cv in enumerate(cr.vertical_connectors):
                    area = world.intersection(physical.region(cv)).area
                    if area > 1e-8:
                        rebuilt.append((c, m, cp, s['port_permutation'][local_port],
                                        area/(cv.w*cv.h), area/local_region.area))
    reference = sorted(geometry.routes)
    rebuilt.sort()
    if len(rebuilt) != len(reference) or any(a[:4] != b[:4] for a, b in zip(rebuilt, reference)):
        raise ValueError('Rotated regional connectivity changed')
    cap_error = max(abs(a[i]-b[i]) for a, b in zip(rebuilt, reference) for i in (4, 5))
    if cap_error > 1e-8:
        raise ValueError('Overlap capacity fractions changed')
    wire_original = wire_rotated = 0.
    byte_error = 0.
    for instance in orientation:
        m, degrees, wanted = instance['memory'], instance['degrees'], instance['selected_port']
        s = next(s for s in symmetry if s['degrees'] == degrees)
        for b, bp in enumerate(s['bank_permutation']):
            # Whole-bank striping in this frozen candidate is invariant under
            # the bank permutation. This is checked, not assumed for all layouts.
            for row in design.layout.shares:
                byte_error = max(byte_error, abs(row[m*nb+b]-row[m*nb+bp]))
            for p in (0, 2):
                wire_original += sum(abs(geometry.bank_xy[b][i]-geometry.port_xy[p][i]) for i in (0, 1))
                target = 0 if p == 0 else wanted
                wire_rotated += sum(abs(geometry.bank_xy[bp][i]-geometry.port_xy[target][i]) for i in (0, 1))
    if byte_error > 1e-12 or abs(wire_original-wire_rotated) > 1e-7:
        raise ValueError('Rotation changed frozen data or point-wire proxy')
    # Wiring-only redirection is not a free port rename: even the straight
    # Manhattan route between endpoints has nonzero length (not routed PPA).
    delta = sum(abs(geometry.port_xy[2][i]-geometry.port_xy[3][i]) for i in (0, 1))
    inputs = ['w2w/analysis/template_binding.py', 'w2w/synthesis/provisioning_catalog.py',
              'w2w/service/guaranteed_service_exchange.py', 'Reticle.py']
    return dict(schema='w2w.template-binding-audit.v1',
                source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                source_sha256={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs},
                frozen_layout_sha256=design.layout.sha256,
                direction_counts=dict(Counter(design.shared_directions)), symmetries=symmetry,
                uniform_fixed_direction=uniform,
                conditional_instance_rotation=dict(instances=orientation,
                    orientation_counts=dict(Counter(v['degrees'] for v in orientation)),
                    rebuilt_overlap_edges=len(rebuilt), maximum_capacity_fraction_error=cap_error,
                    maximum_static_byte_fraction_error=byte_error,
                    selected_home_shared_wire_mm_per_memory=wire_rotated/len(orientation),
                    identical_point_wire_proxy=True,
                    status='Geometric witness conditional on per-instance orientation and bank/address relabeling'),
                wiring_only=dict(port2_to_port3_manhattan_mm=delta,
                    status='A direct far-port redirection requires wiring; bank-side alternative needs a separate layout and cost'),
                manufacturing=dict(uniform_orientation_policy='No single fixed direction covers this frozen deployment',
                    per_instance_rotation='Region-level witness exists, but process/reticle exposure and full-template legality unverified',
                    unknown=['HB pad bit order and signals', 'command/control/clock/reset/PDN correspondence',
                             'actual DRAM macro bank/address orientation', 'lithography orientation policy',
                             'full source+wire+RX timing and area']),
                interpretation='Keep pruned source as a conditional strong baseline; neither claim it impossible nor claim a manufactured rotated implementation')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(direction_counts=result['direction_counts'],
        orientation_counts=result['conditional_instance_rotation']['orientation_counts'],
        rebuilt_edges=result['conditional_instance_rotation']['rebuilt_overlap_edges'],
        uniform_maximum_nonhome=[r['balanced_layout_relaxation']['maximum_total_nonhome_fraction']
                                for r in result['uniform_fixed_direction']])))


if __name__ == '__main__':
    main()
