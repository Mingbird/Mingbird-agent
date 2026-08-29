"""Module m04: calc_slope."""


def calc_slope(values, factor=1.0):
    n = len(values)
    sx = sum(range(n))
    sy = sum(values)
    return sy / sx if sx else 0.0   # BUG: not least-squares slope
