"""Module m03: calc_variance."""


def calc_variance(values, factor=1.0):
    m = sum(values) / len(values)
    return sum((v - m) ** 2 for v in values) / len(values)   # BUG: population, should be sample (n-1)
