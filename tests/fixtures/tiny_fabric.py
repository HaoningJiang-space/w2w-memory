"""Two computes, two memories, one native bank per memory, explicit HB routes."""
from fractions import Fraction
from w2w.domain import Geometry, Exposure, StaticLayout, MemoryFabricDesign, EndpointSpec


def two_compute_two_memory(widths=(256, 128, 128), depths=(1, 1, 1),
                           home_fraction=Fraction(2, 3), mode='buffered'):
    fraction = Fraction(home_fraction)
    geometry = Geometry('2C2M', ((0., 0.), (1., 0.)), ((0., 0.), (1., 0.)),
                        ((0, 0, 0, 0, 1., 1.), (1, 1, 0, 0, 1., 1.),
                         (1, 0, 2, 1, 1., 1.), (0, 1, 1, 2, 1., 1.)),
                        ((0., 0.),), ((0., 0.), (-1., 0.), (1., 0.)))
    exposure = Exposure(((0, 1, 2),), (8000, 8000, 8000), bank_bw=1.,
                        object_gib=1., bank_capacity_gib=2.)
    layout = StaticLayout(((float(fraction), float(1-fraction)),
                           (float(1-fraction), float(fraction))))
    return MemoryFabricDesign('tiny', 'pair', geometry, exposure,
                              EndpointSpec(widths, depths, mode=mode), layout, fraction)
