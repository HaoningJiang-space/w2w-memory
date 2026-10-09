"""Coordinate-derived rectangular candidate; assumptions, not foundry calibration.

This exporter changes physical links in an existing SystemSpec. Logical tile IDs,
memory capacities, workload owners and all execution resources remain unchanged.
"""
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from math import ceil


@dataclass(frozen=True)
class WaferRecipe:
    diameter_um: int = 300000
    edge_exclusion_um: int = 1000
    field_width_um: int = 26000
    field_height_um: int = 33000
    gap_um: int = 100
    pipeline_spacing_um: int = 2000
    hb_height_um: int = 20
    hb_cycles: int = 1
    credit_width_bits: int = 1  # one returned credit pulse per VC/cycle

    def __post_init__(self):
        for key, value in asdict(self).items():
            if type(value) is not int or value < (0 if key in ('gap_um', 'edge_exclusion_um') else 1):
                raise ValueError('Invalid geometric recipe: '+key)
        if 2*self.edge_exclusion_um >= self.diameter_um:
            raise ValueError('No usable wafer area')


def from_coordinates(spec, recipe=WaferRecipe()):
    """Aligned rectangle layers, center routers/MCs and only home HB overlaps."""
    xs, ys = [t.x for t in spec.tiles], [t.y for t in spec.tiles]
    columns, rows = max(xs)+1, max(ys)+1
    if min(xs) != 0 or min(ys) != 0 or len(spec.tiles) != columns*rows:
        raise ValueError('Candidate requires a complete rectangular logical mesh')
    if len({t.reticle for t in spec.tiles}) != len(spec.tiles):
        raise ValueError('First geometric candidate has one aggregate tile per reticle')
    positions, reticles = {}, []
    radius2 = (recipe.diameter_um-2*recipe.edge_exclusion_um)**2
    for t in spec.tiles:
        x2 = (2*t.x-columns+1)*(recipe.field_width_um+recipe.gap_um)
        y2 = (2*t.y-rows+1)*(recipe.field_height_um+recipe.gap_um)
        corners2 = [(x2+dx*recipe.field_width_um, y2+dy*recipe.field_height_um)
                    for dx,dy in ((-1,-1),(1,-1),(1,1),(-1,1))]
        if any(x*x+y*y > radius2 for x,y in corners2):
            raise ValueError('Reticle outside usable wafer circle')
        positions[t.id] = (x2/2, y2/2)
        reticles.append(dict(id=t.reticle, tile=t.id, center_um=positions[t.id],
                             polygon_um=[(x/2,y/2) for x,y in corners2]))
    for m in spec.memories:
        if m.home_tile not in positions:
            raise ValueError('Unknown home attachment')
        positions[m.id] = positions[m.home_tile]
    links, paths = [], []
    for link in spec.links:
        a, b = positions[link.src], positions[link.dst]
        if link.kind == 'HB':
            memory = next((m for m in spec.memories if m.id in (link.src,link.dst)), None)
            if memory is None or memory.home_tile not in (link.src,link.dst) or a != b:
                raise ValueError('No legal overlap for a non-home HB')
            length, cycles = recipe.hb_height_um, recipe.hb_cycles
            points = [(a[0],a[1],0),(b[0],b[1],recipe.hb_height_um)]
            if link.src in {m.id for m in spec.memories}: points.reverse()
        else:
            length = int(abs(a[0]-b[0])+abs(a[1]-b[1]))
            if (a[0] != b[0]) == (a[1] != b[1]):
                raise ValueError('Only straight nearest-neighbor stitched paths')
            cycles = ceil(length/recipe.pipeline_spacing_um)
            points = [(a[0],a[1],0),(b[0],b[1],0)]
        links.append(replace(link,length_um=length,pipeline_cycles=cycles,credit_cycles=cycles))
        paths.append(dict(resource_id=link.resource_id, points_um=points, length_um=length,
            data_bits=link.width_bits, data_cycles=cycles, credit_cycles=cycles,
            data_wire_bit_mm=link.width_bits*length/1000,
            link_register_bits=link.width_bits*cycles,
            credit_wire_bit_mm=recipe.credit_width_bits*length/1000,
            credit_register_bits=recipe.credit_width_bits*cycles,
            credit_window_flits=spec.input_buffer_flits,
            propagation_only_flits_per_cycle_upper=min(1,spec.input_buffer_flits/(2*cycles))))
    exported = replace(spec, links=tuple(links))
    record = dict(schema='w2w.wafer-machine.v1', scope='coordinate_derived_un calibrated_candidate'.replace(' ',''),
        recipe=asdict(recipe), compute_reticles=reticles,
        memory_placement='identical aligned rectangles; home overlap only', paths=paths,
        assumptions=dict(field='26x33 mm field scale, WoW paper; not a DRAM macro floorplan',
            pipeline='2 mm/cycle from published modeling recipe, not signoff',
            gap_edge_and_hb='100 um gap, 1 mm exclusion, 20 um/one-cycle HB are declared assumptions',
            ports='one center router/MC per reticle; native array access is in DRAM backend',
            credit='one pulse per VC per cycle; clock/control/P/G cost not calibrated'),
        sources=['https://arxiv.org/html/2603.05266v1'], area_um2=None, energy_j=None)
    record['machine_sha256'] = sha256(json.dumps([asdict(exported),record],sort_keys=True).encode()).hexdigest()
    return exported, record
