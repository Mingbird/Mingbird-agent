"""Module m07: calc_normalize."""


def calc_normalize(values, factor=1.0):
    mx = max(values)
    return [v * mx for v in values]   # BUG: multiply instead of divide
