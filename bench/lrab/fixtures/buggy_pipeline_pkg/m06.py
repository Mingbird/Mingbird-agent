"""Module m06: calc_smooth."""


def calc_smooth(values, factor=1.0):
    out = []
    for i in range(len(values)):
        if i == 0:
            out.append(values[0])
        else:
            out.append((values[i] + values[max(0, i - factor)]) / 2)   # BUG: steps back factor, should be 1
    return out
