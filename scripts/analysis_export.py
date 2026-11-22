#!/usr/bin/env python3
"""Build audit-friendly NBA EDGE calibration diagnostics and ChatGPT daily export.

Reads published files only: never contacts a sportsbook or consumes Odds API credits.
This is a retrospective diagnostic, NOT a calibrated prediction model.
"""
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from calibration_audit import audit
from shadow_projections import report as shadow_report
from performance_diagnostics import inspect_settlements, projection_replay, frozen_projection_accuracy
from model_comparison import compare as compare_models
from context_research import compare_context
from ranking_experiment import report as ranking_report
from projection_shadow import report as projection_shadow_report
from gap_threshold_experiment import report as gap_threshold_report
from evidence_walkforward import report as evidence_walkforward_report

DOCS = Path(__file__).resolve().parents[1] / "docs"
VALID = {"win", "loss", "push"}


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def safe_probability(value):
    try:
        p = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return p if math.isfinite(p) and 0 < p < 1 else None


def decimal_profit(american):
    try:
        price = float(american)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(price) or price == 0:
        return None
    return price / 100 if price > 0 else 100 / -price


def summarize(picks):
    settled = [p for p in picks if p.get("result") in VALID]
    decisions = [p for p in settled if p["result"] in ("win", "loss")]
    probabilities = [(safe_probability(p.get("probability")), int(p["result"] == "win"))
                     for p in decisions]
    probabilities = [(p, y) for p, y in probabilities if p is not None]
    wins = sum(p["result"] == "win" for p in decisions)
    pushes = len(settled) - len(decisions)
    valid_units = []
    for p in decisions:
        profit = decimal_profit(p.get("odds"))
        if profit is not None:
            valid_units.append(profit if p["result"] == "win" else -1.0)
    n = len(probabilities)
    brier = sum((p - y) ** 2 for p, y in probabilities) / n if n else None
    log_loss = (-sum(y * math.log(p) + (1-y) * math.log1p(-p)
                     for p, y in probabilities) / n if n else None)
    buckets = []
    for lo in range(0, 100, 10):
        group = [(p, y) for p, y in probabilities
                 if lo / 100 <= p < (lo + 10) / 100]
        buckets.append({"range": f"{lo}-{lo+10}%", "n": len(group),
                        "predicted": round(sum(p for p, _ in group) / len(group), 4) if group else None,
                        "observed": round(sum(y for _, y in group) / len(group), 4) if group else None})
    total_units = sum(valid_units)
    return {"settled": len(settled), "graded": len(decisions), "wins": wins,
            "losses": len(decisions)-wins, "pushes": pushes,
            "pending": sum(p.get("result") == "pending" for p in picks),
            "winRate": round(wins/len(decisions), 4) if decisions else None,
            "units": round(total_units, 4),
            "roi": round(total_units / len(valid_units), 4) if valid_units else None,
            "probabilitySamples": n, "meanPredictedProbability":
                round(sum(p for p, _ in probabilities)/n, 4) if n else None,
            "observedHitRate": round(sum(y for _, y in probabilities)/n, 4) if n else None,
            "brierScore": round(brier, 5) if brier is not None else None,
            "logLoss": round(log_loss, 5) if log_loss is not None else None,
            "calibrationBuckets": buckets}


def build(snapshot, ledger, generated_at, logs=None, injury_review=None, context_backfill=None, ranking_state=None, projection_shadow_state=None, gap_threshold_state=None):
    picks = ledger.get("picks", [])
    by_market = defaultdict(list)
    by_side = defaultdict(list)
    by_grade = defaultdict(list)
    by_slate = defaultdict(list)
    by_market_side = defaultdict(list)
    for p in picks:
        market = str(p.get("market", "unknown"))
        side = str(p.get("side", "unknown"))
        by_market[market].append(p)
        by_side[side].append(p)
        by_grade[str(p.get("grade", "unknown"))].append(p)
        by_slate[str(p.get("slate", "unknown"))].append(p)
        by_market_side[(market, side)].append(p)
    verified = [p for p in picks if p.get("settlementStatus") == "verified_matchup_and_start"]
    legacy = [p for p in picks if p.get("result") in VALID
              and p.get("settlementStatus") != "verified_matchup_and_start"]
    report = {
        "schemaVersion": 3,
        "generatedAt": generated_at,
        "slateDate": snapshot.get("slateDate"),
        "snapshotUpdatedAt": snapshot.get("updatedAt"),
        "oddsSnapshotAt": snapshot.get("oddsSnapshotAt"),
        "refreshStatus": snapshot.get("refreshStatus"),
        "modelVersion": snapshot.get("modelVersion"),
        "selectionDiagnostics": snapshot.get("selectionDiagnostics", {"status":"not_collected"}),
        "evidenceResearch": snapshot.get("evidenceResearch", {"status":"not_collected"}),
        "evidenceScoreWalkForward": evidence_walkforward_report(logs or []),
        "modelStatus": "uncalibrated",
        "calibrationMethod": "diagnostic_only_no_probability_adjustment",
        "walkForwardBacktest": audit(picks),
        "shadowProjectionResearch": shadow_report(snapshot, logs or []),
        "settlementAudit": inspect_settlements(picks, logs or []),
        "historicalPickProjectionReplay": projection_replay(picks, logs or []),
        "frozenProjectionAccuracy": frozen_projection_accuracy(picks),
        "modelHeadToHead": compare_models(logs or []),
        "contextResearch": compare_context(logs or []),
        "rankingExperiment": ranking_report(ranking_state or {}),
        "projectionShadow": projection_shadow_report(projection_shadow_state or {}),
        "normalizedGapExperiment": gap_threshold_report(gap_threshold_state or {}),
        "contextBackfill": context_backfill if context_backfill is not None else {"status":"not_started"},
        "injuryReview": injury_review if injury_review is not None else {"reportingStatus":"unavailable","productionChanges":False,"picks":[]},
        "calibration": {
            "overall": summarize(picks),
            "verifiedOnly": summarize(verified),
            "legacyUnverified": summarize(legacy),
            "verifiedSettledCount": sum(p.get("result") in VALID for p in verified),
            "legacySettledCount": len(legacy),
            "byMarket": {k: summarize(v) for k, v in sorted(by_market.items())},
            "bySide": {k: summarize(v) for k, v in sorted(by_side.items())},
            "byGrade": {k: summarize(v) for k, v in sorted(by_grade.items())},
            "bySlate": {k: summarize(v) for k, v in sorted(by_slate.items())},
            "byMarketAndSide": {m: {side: summarize(v) for (market, side), v in sorted(by_market_side.items()) if market == m}
                                for m in sorted(by_market)},
            "minimumSuggestedSettledSample": 200,
            "sufficientForCalibration": False,
            "note": "Overall and by-market summaries include older legacy settlements. Use verifiedOnly for event-confirmed outcomes. Neither proves positive EV; do not train on in-sample data.",
        },
        "today": {
            "eventsChecked": snapshot.get("eventsChecked"),
            "propsScanned": snapshot.get("propsScanned"),
            "ranked": snapshot.get("ranked", []),
            "warnings": snapshot.get("warnings", []),
        },
        "reviewChecklist": [
            "Verify game date, team, and actual player availability before relying on the pick.",
            "Check injury reports, projected minutes, rotations and rest; model lacks injury adjustment.",
            "Confirm live bookmaker price and line; this export may contain stale odds.",
            "Recalculate EV if odds change; probability is uncalibrated.",
            "Flag correlated props and insufficient history; passing is acceptable.",
            "Check bySide/byMarketAndSide for directional model bias; small samples are inconclusive.",
            "Review settlementAudit discrepancies before trusting historical win rates.",
        ],
        "settlementCaveat": "New settlements require a matching matchup, game start time and unique ESPN game boxscore. Older results remain unverified legacy records; sportsbook and ESPN event IDs come from different providers and are not directly equal.",
        "isBettingAdvice": False,
    }
    return report


def main():
    snapshot = read_json(DOCS / "data.json", {})
    ledger = read_json(DOCS / "tracker.json", {"picks": []})
    game_data = read_json(DOCS / "game_logs.json", {"logs": []})
    logs = game_data.get("logs", [])
    injury_review = read_json(DOCS / "injury_review.json", None)
    ranking_state = read_json(DOCS / "ranking_experiment.json", {"slates":{}})
    projection_state = read_json(DOCS / "projection_shadow.json", {"slates":{}})
    gap_state = read_json(DOCS / "gap_threshold_experiment.json", {"slates":{}})
    report = build(snapshot, ledger, datetime.now(timezone.utc).isoformat(),
                   logs, injury_review, game_data.get("contextBackfill"), ranking_state, projection_state, gap_state)
    (DOCS / "daily_analysis.json").write_text(
        json.dumps(report, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8")
    overall = report["calibration"]["overall"]
    print(f"Analysis export generated; graded={overall['graded']}, brier={overall['brierScore']}; 0 odds API requests")


if __name__ == "__main__":
    main()
