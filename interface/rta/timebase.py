"""DHO800/900 time-base grids; DHO802 readback verified on firmware 00.01.05."""
import math

PS_PER_SECOND = 10**12
def build_timebase(min_seconds, max_seconds):
    minimum, maximum = round(min_seconds * PS_PER_SECOND), round(max_seconds * PS_PER_SECOND)
    coarse = sorted({factor * 10**power for power in range(3, 16) for factor in (1, 2, 5)
                     if minimum <= factor * 10**power <= maximum})
    return dict(min_ps=minimum, max_ps=maximum,
                bands=[dict(start_ps=a, end_ps=b, step_ps=max(100, b//100))
                       for a, b in zip(coarse, coarse[1:])])


TIMEBASE = build_timebase(5e-9, 500)


def band_for(ps, grid=TIMEBASE):
    return next((b for b in grid["bands"] if ps < b["end_ps"]), grid["bands"][-1])


def floor_time(seconds, grid=TIMEBASE):
    ps = max(grid["min_ps"], min(grid["max_ps"], round(seconds * PS_PER_SECOND)))
    band = band_for(ps, grid)
    return (band["start_ps"] + (ps-band["start_ps"])//band["step_ps"]*band["step_ps"]) / PS_PER_SECOND


def next_time(seconds, grid=TIMEBASE):
    floor = floor_time(seconds, grid)
    if floor >= grid["max_ps"] / PS_PER_SECOND:
        return floor
    ps = round(floor * PS_PER_SECOND)
    return (ps + band_for(ps, grid)["step_ps"]) / PS_PER_SECOND


def format_time(seconds):
    for label, factor in (("s", 1), ("ms", 1e3), ("µs", 1e6), ("ns", 1e9)):
        if seconds * factor >= 1 or label == "ns":
            return f"{seconds * factor:.12g} {label}"


def valid_time(seconds, grid=TIMEBASE):
    return (math.isfinite(seconds) and
            grid["min_ps"] <= seconds * PS_PER_SECOND <= grid["max_ps"] and
            math.isclose(seconds, floor_time(seconds, grid), rel_tol=1e-12, abs_tol=1e-20))
