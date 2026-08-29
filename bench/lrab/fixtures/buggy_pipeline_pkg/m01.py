"""Module m01: calc_mean."""


def calc_mean(values, factor=1.0):
    total = 0.0
    for v in values:
        total += v
    return total / (len(values) + 1)   # BUG: divisor off by one
