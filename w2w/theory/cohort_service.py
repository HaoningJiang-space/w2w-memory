"""Pure work-conservation facts for static service-aware object placement."""
from fractions import Fraction


def pair_score(a, b, home_fraction):
    """Native work of a capacity-matched reciprocal pair, lambda >= 1/2."""
    f = Fraction(home_fraction)
    if not Fraction(1, 2) <= f <= 1 or min(a, b) < 0:
        raise ValueError('Nonnegative work and reciprocal fraction >= 1/2 required')
    return Fraction(a+b, 2) + (f-Fraction(1, 2))*abs(a-b)


def independent_object_floor_possible(left_fractions, right_fractions):
    """Native-load feasibility for any independently chosen unit-demand pair."""
    left, right = tuple(map(Fraction, left_fractions)), tuple(map(Fraction, right_fractions))
    if not left or not right or any(not 0 <= f <= 1 for f in left+right):
        raise ValueError('Nonempty fractions in [0,1] required')
    return max(left) <= min(right) and max(right) <= min(left)


def native_full_load_limits(object_fractions):
    """Worst native-memory load for independent object choices at all computes.

Input [compute][object][memory], unit compute demand and unit memory supply,
equal compute/memory count, no replicas or request substitution. This checks
native resources only; paths and finite execution impose further constraints.
"""
    nc = len(object_fractions)
    rows = [tuple(tuple(map(Fraction, obj)) for obj in objects) for objects in object_fractions]
    if not nc or any(not objects for objects in rows) or any(
            len(obj) != nc or sum(obj) != 1 or any(v < 0 for v in obj) for objects in rows for obj in objects):
        raise ValueError('Require nonempty unit fractions on a square native fabric')
    maximum = [sum(max(obj[m] for obj in objects) for objects in rows) for m in range(nc)]
    uniform = all(all(obj == objects[0] for obj in objects) for objects in rows)
    feasible = max(maximum) <= 1
    if feasible and not uniform:
        raise AssertionError('Work conservation requires identical per-compute object fractions')
    return dict(worst_native_loads=[str(v) for v in maximum], native_floor_feasible=feasible,
                per_compute_object_fractions_identical=uniform,
                uniform_service_scale=str(1/max(maximum)),
                scope='Native aggregate feasibility only, under independent arbitrary full-load object choices')
