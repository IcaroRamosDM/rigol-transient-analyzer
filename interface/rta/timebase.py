"""DHO802 time-base grid; readback verified on firmware 00.01.05."""
import math

PS_PER_SECOND = 10**12
coarse = sorted({factor * 10**power for power in range(3, 16) for factor in (1, 2, 5)
                 if 5000 <= factor * 10**power <= 10**15})
TIMEBASE = dict(min_ps=coarse[0], max_ps=coarse[-1],
                bands=[dict(start_ps=a, end_ps=b, step_ps=b//100)
                       for a, b in zip(coarse, coarse[1:])])


def band_for(ps):
    return next((b for b in TIMEBASE["bands"] if ps < b["end_ps"]), TIMEBASE["bands"][-1])


def floor_time(seconds):
    ps = max(TIMEBASE["min_ps"], min(TIMEBASE["max_ps"], round(seconds * PS_PER_SECOND)))
    band = band_for(ps)
    return (band["start_ps"] + (ps-band["start_ps"])//band["step_ps"]*band["step_ps"]) / PS_PER_SECOND


def next_time(seconds):
    floor = floor_time(seconds)
    if floor >= TIMEBASE["max_ps"] / PS_PER_SECOND:
        return floor
    ps = round(floor * PS_PER_SECOND)
    return (ps + band_for(ps)["step_ps"]) / PS_PER_SECOND


def format_time(seconds):
    for label, factor in (("s", 1), ("ms", 1e3), ("µs", 1e6), ("ns", 1e9)):
        if seconds * factor >= 1 or label == "ns":
            return f"{seconds * factor:.12g} {label}"


def valid_time(seconds):
    return (math.isfinite(seconds) and
            TIMEBASE["min_ps"] <= seconds * PS_PER_SECOND <= TIMEBASE["max_ps"] and
            math.isclose(seconds, floor_time(seconds), rel_tol=1e-12, abs_tol=1e-20))
