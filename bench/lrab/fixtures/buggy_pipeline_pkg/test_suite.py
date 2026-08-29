"""Test suite for buggy_pipeline_pkg. Run: python test_suite.py"""
import importlib, traceback

CASE = [1.0, 2.0, 3.0, 4.0]
# (module, function, expected result on CASE with factor=2)
EXPECTED = [
    ("m01", "calc_mean", 2.5),
    ("m02", "calc_median", 2.5),
    ("m03", "calc_variance", 5 / 3),
    ("m04", "calc_slope", 1.0),
    ("m05", "calc_interp", [3.0, 4.0, 5.0]),
    ("m06", "calc_smooth", [1.0, 1.5, 2.5, 3.5]),
    ("m07", "calc_normalize", [0.25, 0.5, 0.75, 1.0]),
    ("m08", "calc_integrate", 7.5),
    ("m09", "calc_roots", 1),
    ("m10", "calc_fit", 1.0),
]

def close(a, b):
    if isinstance(b, list):
        return isinstance(a, list) and len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))
    if isinstance(b, (int, float)) and isinstance(a, (int, float)) and not isinstance(a, bool):
        return abs(a - b) < 1e-9
    return a == b

def main():
    passed = failed = 0
    for mod, fn, want in EXPECTED:
        try:
            m = importlib.import_module(mod)
            f = getattr(m, fn)
            got = f(CASE, 2)
            if close(got, want):
                print(f'PASS {mod}.{fn}')
                passed += 1
            else:
                print(f'FAIL {mod}.{fn}: got {got!r}, want {want!r}')
                failed += 1
        except Exception as e:
            print(f'FAIL {mod}.{fn}: {type(e).__name__}: {e}')
            failed += 1
    print(f'{passed} passed, {failed} failed')

if __name__ == "__main__":
    main()
