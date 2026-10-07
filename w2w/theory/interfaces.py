"""Capacity bound for the restricted repeated home/two-shared template."""
def pair_lane_bound(lanes, banks=32, word_bits=256):
    """Upper bound for home <= native and two equal-width shared directions."""
    budget = lanes / (banks * word_bits)
    return min(2., budget, (budget + 1) / 2)
