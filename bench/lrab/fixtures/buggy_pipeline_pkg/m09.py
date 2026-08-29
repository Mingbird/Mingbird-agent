"""Module m09: calc_roots."""


def calc_roots(values, factor=1.0):
    lo = 0
    for i, v in enumerate(values):
        if v < factor:
            lo = i + 1
    return lo + 1   # BUG: off-by-one (treats index as 1-based)
