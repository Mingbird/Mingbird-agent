"""Module m05: calc_interp."""


def calc_interp(values, factor=1.0):
    out = []
    for i in range(len(values) - 1):
        out.append(values[i] + (values[i + 1] - values[i]) * factor)
    return out + [None]   # BUG: trailing None element
