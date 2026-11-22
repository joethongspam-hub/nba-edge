"""Audit settled NBA EDGE picks without changing historical results.

Uses only existing tracker and ESPN game logs; no external requests.
Legacy matches are retrospective corroboration, never a rewrite to verified.
"""
from collections import defaultdict
from datetime import datetime, timezone
import math

from prop_markets import stat_value
from settlement import unique_verified_log
from shadow_projections import name_key, project

SETTLED = {"win", "loss", "push"}


def finite(value):
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def outcome(side, actual, line):
    if side not in ("Over", "Under"):
        return None
    if actual == line:
        return "push"
    return "win" if (actual > line) == (side == "Over") else "loss"


def inspect_settlements(picks, logs):
    """Retrospectively reconcile recorded outcomes with identifiable boxscores.

    Do not silently promote older records to officially verified, even if
    the stored settlement agrees with an ESPN game log.
    """
    by_player = defaultdict(list)
    for row in logs:
        by_player[name_key(row.get("player"))].append(row)
    counts = defaultdict(int)
    rows = []
    for p in picks:
        if p.get("result") not in SETTLED:
            continue
        verified = p.get("settlementStatus") == "verified_matchup_and_start"
        match = unique_verified_log(p, by_player[name_key(p.get("player"))])
        status = "missing_matching_log"
        reconstructed = None
        if match is not None:
            actual = stat_value(match, p.get("market"))
            line = finite(p.get("line"))
            original = finite(p.get("actual"))
            reconstructed = outcome(p.get("side"), actual, line) if line is not None else None
            if reconstructed is None:
                status = "invalid_line_or_side"
            elif original is not None and not math.isclose(original, actual, abs_tol=0.01):
                status = "actual_mismatch"
            elif reconstructed != p.get("result"):
                status = "outcome_mismatch"
            else:
                status = "confirmed_verified" if verified else "legacy_corroborated"
        counts[status] += 1
        rows.append({
            "id": p.get("id"), "slate": p.get("slate"),
            "player": p.get("player"), "market": p.get("market"),
            "recordedResult": p.get("result"),
            "recordedActual": p.get("actual"),
            "reconstructedResult": reconstructed,
            "reviewStatus": status, "originallyVerified": verified,
        })
    return {
        "statusCounts": dict(sorted(counts.items())),
        "reviewedSettlements": len(rows),
        "issuesForManualReview": sum(counts[k] for k in (
            "missing_matching_log", "actual_mismatch",
            "outcome_mismatch", "invalid_line_or_side")),
        "records": rows,
        "note": "Retrospective corroboration is not the same as originally verified settlement. Audit never changes saved outcomes or training eligibility.",
    }


def projection_replay(picks, logs):
    """As-of-slate shadow projection audit for settled picks, not stored forecasts."""
    by_player = defaultdict(list)
    for game in logs:
        by_player[name_key(game.get("player"))].append(game)
    rows = []
    for p in picks:
        if p.get("result") not in ("win", "loss"):
            continue
        slate = p.get("slate")
        # Recorded date is used as a conservative cutoff. Do not look at
        # game logs from the target slate or later.
        if not isinstance(slate, str) or len(slate) != 10:
            continue
        stats = project(by_player[name_key(p.get("player"))],
                        p.get("market"), before_date=slate)
        actual = finite(p.get("actual"))
        if stats is None or actual is None:
            continue
        prediction = stats["projectedStat"]
        # Reconstructed projection is explicitly NOT the original model's
        # locked pregame forecast; keep it separate from historical EV.
        rows.append({
            "slate": slate, "player": p.get("player"),
            "market": p.get("market"), "side": p.get("side"),
            "result": p.get("result"), "actual": actual,
            "shadowProjection": prediction,
            "error": round(prediction - actual, 3),
            "absoluteError": round(abs(prediction - actual), 3),
            "predictedMinutes": stats["projectedMinutes"],
            "sample": stats["sample"], "flags": stats["flags"],
        })
    def group(items):
        count = len(items)
        return {
            "n": count,
            "MAE": round(sum(x["absoluteError"] for x in items) / count, 3) if count else None,
            "meanSignedError": round(sum(x["error"] for x in items) / count, 3) if count else None,
            "flaggedUnstableMinutes": sum("unstable_minutes" in x["flags"] for x in items),
            "flaggedMinutesShift": sum("recent_minutes_shift" in x["flags"] for x in items),
        }
    by_market = defaultdict(list)
    by_side = defaultdict(list)
    for row in rows:
        by_market[row["market"]].append(row)
        by_side[row["side"]].append(row)
    return {
        "status": "retrospective_shadow_only",
        "sample": len(rows), "overall": group(rows),
        "byMarket": {k: group(v) for k, v in sorted(by_market.items())},
        "bySide": {k: group(v) for k, v in sorted(by_side.items())},
        "rows": rows,
        "note": "Shadow estimates are reconstructed using only games strictly before the recorded slate; not original frozen forecasts, not matchup/injury adjusted, not proof of expected value.",
    }
