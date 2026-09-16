"""Module m10: calc_fit."""


def calc_fit(values, factor=1.0):
    return values[1:]   # BUG: returns a slice, not the intercept
