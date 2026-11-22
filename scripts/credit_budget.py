"""Fail-closed Odds API credit budget safeguards.

The live remaining quota is obtained from a *free* /events request.
We reserve credits and preflight the WHOLE slate (no partial game scanning).
"""
DEFAULT_RESERVE = 2000
# 8 player prop markets in one US region; 4 credits of per-event headroom.
MAX_EVENT_COST = 12


class OddsBudgetError(RuntimeError):
    pass


def remaining_from_headers(headers):
    value = headers.get("x-requests-remaining")
    if value is None:
        raise OddsBudgetError("Live Odds API quota unavailable; paid requests paused")
    try:
        remaining = int(value)
    except (ValueError, TypeError):
        raise OddsBudgetError("Invalid Odds API quota header; paid requests paused")
    if remaining < 0:
        raise OddsBudgetError("Invalid negative Odds API quota; paid requests paused")
    return remaining


def check_budget(remaining, events_remaining, reserve=DEFAULT_RESERVE,
                 worst_cost=MAX_EVENT_COST):
    if events_remaining < 0 or reserve < 0 or worst_cost <= 0:
        raise ValueError("Invalid budget configuration")
    needed = reserve + events_remaining * worst_cost
    if remaining < needed:
        raise OddsBudgetError(
            f"Odds API budget guard: {remaining} remaining; need at least {needed} "
            f"for full slate ({events_remaining} games) and {reserve} reserve. "
            "No additional paid requests made.")
    return True
