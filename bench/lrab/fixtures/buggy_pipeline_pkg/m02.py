"""Module m02: calc_median."""


def calc_median(values, factor=1.0):
    vs = sorted(values)
    n = len(vs)
    return vs[n // 2]   # BUG: wrong median for even n
