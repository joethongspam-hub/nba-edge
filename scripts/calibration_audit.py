"""Chronological, diagnostics-only probability backtest for NBA EDGE.

Only event-verified historical picks qualify. Each evaluated slate is predicted
using strictly earlier slates; no active-prop probabilities are modified.
No paid odds endpoint or network access is used.
"""
from collections import defaultdict
from datetime import datetime, timezone
import math

MIN_TRAIN = 100
MIN_TEST = 30
CANDIDATE_WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)


def valid_record(record):
    if record.get("settlementStatus") != "verified_matchup_and_start":
        return None
    if record.get("result") not in ("win", "loss"):
        return None
    try:
        p = float(record["probability"])
        recorded = datetime.fromisoformat(record["recordedAt"].replace("Z", "+00:00"))
        start = datetime.fromisoformat(record["startsAt"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if recorded.tzinfo is None or start.tzinfo is None or not math.isfinite(p) or not 0 < p < 1:
        return None
    # Reject records that appear to have been published after tipoff.
    if recorded.astimezone(timezone.utc) >= start.astimezone(timezone.utc):
        return None
    slate = record.get("slate")
    if not isinstance(slate, str) or len(slate) != 10:
        return None
    try:
        slate_date = datetime.strptime(slate, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (slate_date, p, int(record["result"] == "win"))


def brier(pairs):
    return sum((p-y)**2 for p, y in pairs)/len(pairs) if pairs else None


def calibrated(p, weight):
    # Fixed neutral benchmark: p=0.5. This is a shrinkage diagnostic,
    # not a fitted injury-aware predictive model.
    return 0.5 + weight * (p - 0.5)


def best_weight(training):
    # Penalize deviation from unchanged probabilities to avoid tuning
    # too aggressively to a small training dataset.
    return min(CANDIDATE_WEIGHTS,
               key=lambda w: (sum((calibrated(p, w)-y)**2 for p, y in training)/len(training)
                              + 0.001*(1-w)**2, -w))


def examine(picks, min_train=MIN_TRAIN, min_test=MIN_TEST):
    records = sorted((x for r in picks if (x := valid_record(r)) is not None),
                     key=lambda x: x[0])
    dates = sorted({d for d, _, _ in records})
    training = []
    evaluations = []
    folds = 0
    weight_counts = defaultdict(int)
    for slate in dates:
        today = [(p, y) for d, p, y in records if d == slate]
        if len(training) >= min_train:
            weight = best_weight(training)
            weight_counts[str(weight)] += len(today)
            evaluations.extend((p, calibrated(p, weight), y) for p, y in today)
            folds += 1
        # This slate only enters the training set AFTER its prediction,
        # so same-day picks never train on one another.
        training.extend(today)
    ready = len(evaluations) >= min_test
    base = brier([(p,y) for p, _, y in evaluations])
    adjusted = brier([(q,y) for _, q, y in evaluations])
    return {
        "method": "expanding_window_prior_slates_only_shrinkage_backtest",
        "status": "evaluated" if ready else "insufficient_verified_history",
        "minTrainingPicks": min_train,
        "minEvaluationPicks": min_test,
        "verifiedEligible": len(records),
        "excludedUnverifiedOrInvalid": len(picks)-len(records),
        "evaluatedPicks": len(evaluations),
        "evaluationSlates": folds,
        "baselineBrier": round(base, 6) if ready else None,
        "experimentalBrier": round(adjusted, 6) if ready else None,
        "brierImprovement": round(base-adjusted, 6) if ready else None,
        "weightsUsedInEvaluation": dict(weight_counts) if ready else {},
        "autoApply": False,
        "note": "Backtest is diagnostic only. Candidate shrinkage weights are fitted on earlier verified slates; selected picks are a biased subset. Model production probabilities, EV and grades remain unchanged.",
    }


def audit(picks):
    by_market = defaultdict(list)
    for pick in picks:
        by_market[str(pick.get("market", "unknown"))].append(pick)
    return {
        "overall": examine(picks),
        "byMarket": {market: examine(rows) for market, rows in sorted(by_market.items())},
        "productionCalibrationEnabled": False,
    }
