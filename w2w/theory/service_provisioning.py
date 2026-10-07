"""Pure capacity and request-lifetime bounds; no geometry, solver or replay.

These are necessary fluid bounds, not achievable finite-execution guarantees.
"""
from fractions import Fraction

from w2w.workloads.read_trace import integer


def ceil_fraction(value):
    value = Fraction(value)
    return (value.numerator + value.denominator - 1) // value.denominator

def credit_matched_split(banks, shared_rate, window, home_lifetime=3, shared_lifetime=4):
    """Maximize a *necessary steady-rate upper bound* over the home fraction.

    Each bank exports at most one home word/slot and shared_rate shared words/
    slot. A compute may use its home and one peer memory; all bank streams have
    the same reciprocal split. The request window covers issue through delivery.
    Rates/lifetimes are explicit inputs, not inferred from nominal link widths.
    """
    for name, value in (('banks', banks), ('window', window), ('home lifetime', home_lifetime),
                        ('shared lifetime', shared_lifetime)):
        integer(value, name, 1)
    shared_rate = Fraction(shared_rate)
    if not 0 < shared_rate <= 1 or shared_lifetime < home_lifetime:
        raise ValueError('Require 0 < shared rate <= 1 and shared lifetime >= home lifetime')
    native_window = banks * home_lifetime
    capacity_fraction = 1 / (1 + shared_rate)
    if window < native_window:
        fraction = Fraction(1)
    else:
        credit_fraction = Fraction(banks * shared_lifetime,
                                   window + banks * (shared_lifetime - home_lifetime))
        fraction = max(capacity_fraction, credit_fraction)
    rate = steady_rate_bound(banks, shared_rate, fraction, window, home_lifetime, shared_lifetime)
    return dict(home_fraction=str(fraction), capacity_matched_home_fraction=str(capacity_fraction),
                normalized_rate_upper=str(rate), native_window_necessary=native_window,
                baseline_not_excluded=rate >= 1,
                scope='Optimum of the stated steady-rate relaxation, not finite replay or hardware optimum')

def steady_rate_bound(banks, shared_rate, home_fraction, window, home_lifetime=3, shared_lifetime=4):
    """Normalized capacity/lifetime bound; aggregate native capacity is two memories."""
    integer(banks, 'banks', 1)
    integer(window, 'window', 1)
    for value in (home_lifetime, shared_lifetime):
        integer(value, 'word lifetime', 1)
    fraction, shared_rate = Fraction(home_fraction), Fraction(shared_rate)
    if not 0 < fraction <= 1 or not 0 < shared_rate <= 1:
        raise ValueError('Invalid fraction or shared service')
    bounds = [Fraction(2), 1 / fraction,
              Fraction(window, banks) / (fraction * home_lifetime + (1 - fraction) * shared_lifetime)]
    if fraction != 1:
        bounds.append(shared_rate / (1 - fraction))
    return min(bounds)

def pool_capacity_bound(banks, engine_rate, home_fraction, engines, target_rate):
    """Necessary shared-engine count at fixed bank-equivalent capacity and split."""
    integer(banks, 'banks', 1)
    integer(engines, 'engines')
    q, fraction, target = Fraction(engine_rate), Fraction(home_fraction), Fraction(target_rate)
    if not 0 < q <= 1 or not 0 < fraction <= 1 or target <= 0:
        raise ValueError('Invalid pool capacity inputs')
    upper = min(Fraction(2 * banks), banks / fraction)
    if fraction != 1:
        upper = min(upper, engines * q / (1 - fraction))
    return dict(engines=engines, required_shared_words_per_slot=str(target * (1 - fraction)),
                minimum_engines_necessary=ceil_fraction(target * (1 - fraction) / q),
                rate_upper_words_per_slot=str(upper),
                reoptimized_split_normalized_upper=str(min(Fraction(2), 1 + engines * q / banks)),
                scope='Aggregate capacity only; cross-bank binding, input transport and arbitration omitted')
