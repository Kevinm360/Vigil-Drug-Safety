"""Descriptive reporting-share changes, with Newcombe–Wilson intervals.

Method: https://pubmed.ncbi.nlm.nih.gov/9595617/ (method 10, no continuity
correction). Intervals are unadjusted and do not account for reporting bias.
"""
import math
from datetime import date
import re


def validate_periods(value, cohort):
    if not isinstance(value, dict) or set(value) != {"baseline_start", "baseline_end"}:
        raise ValueError("Choose the start and end of the baseline period.")
    dates = []
    for key in ("baseline_start", "baseline_end"):
        raw = value[key]
        if not isinstance(raw, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            raise ValueError("Baseline dates must use YYYY-MM-DD.")
        try:
            dates.append(date.fromisoformat(raw))
        except ValueError:
            raise ValueError("Choose valid baseline dates.") from None
    start, end = dates
    if start > end or start < date(1900, 1, 1) or (end-start).days > 36525:
        raise ValueError("Choose an ordered baseline window of 100 years or less, starting in 1900 or later.")
    if end >= date.fromisoformat(cohort["start"]):
        raise ValueError("The baseline must end before the current period begins. Overlapping periods cannot be compared.")
    return {"baseline_start": start.isoformat(), "baseline_end": end.isoformat()}


def wilson(count, total):
    if total <= 0 or count is None or not 0 <= count <= total:
        return None
    z = 1.959963984540054
    p = count / total
    denominator = 1 + z*z/total
    center = (p + z*z/(2*total)) / denominator
    half = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total)) / denominator
    return (0 if count == 0 else max(0, center-half)), (1 if count == total else min(1, center+half))


def change_row(reaction, before, after, before_total, after_total):
    left, right = wilson(before, before_total), wilson(after, after_total)
    delta = low = high = None
    if left is not None and right is not None:
        a, b = after/after_total, before/before_total
        delta = a-b
        low = max(-1, delta-math.hypot(a-right[0], left[1]-b))
        high = min(1, delta+math.hypot(right[1]-a, b-left[0]))
    direction = "unavailable" if delta is None else "higher" if low > 0 else "lower" if high < 0 else "uncertain"
    return {"reaction": reaction, "baseline_count": before, "current_count": after,
            "count_delta": after-before if after is not None and before is not None else None,
            "baseline_share": before/before_total*100 if left is not None else None,
            "current_share": after/after_total*100 if right is not None else None,
            "share_delta_pp": delta*100 if delta is not None else None,
            "ci_low_pp": low*100 if low is not None else None,
            "ci_high_pp": high*100 if high is not None else None,
            "direction": direction,
            "current_only": bool(left and right and before == 0 and after > 0),
            "baseline_only": bool(left and right and after == 0 and before > 0),
            "sparse": before is not None and after is not None and min(before, after) < 5}
