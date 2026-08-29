"""Module m08: calc_integrate."""


def calc_integrate(values, factor=1.0):
    total = 0
    for v in values:
        total += v
    return total // len(values)   # BUG: integer division
