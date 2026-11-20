#!/usr/bin/env python3
"""Best-effort, public ESPN injury flags for daily ChatGPT review.

No paid odds requests. This does NOT determine official participation,
predict minutes, or alter live NBA EDGE rankings/grades.
"""
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
DOCS = Path(__file__).resolve().parents[1] / "docs"


def norm(value):
    return "".join(c for c in str(value).casefold() if c.isalnum())


def get_name(item):
    athlete = item.get("athlete") or {}
    if isinstance(athlete, dict):
        return athlete.get("displayName") or athlete.get("fullName") or athlete.get("name")
    return None


def get_status(item):
    status = item.get("status")
    if isinstance(status, dict):
        status = status.get("description") or status.get("name")
    if not status:
        status = item.get("type")
    if isinstance(status, dict):
        status = status.get("description") or status.get("name")
    return str(status).strip() if status else "reported_injury_status_unknown"


def extract_injuries(payload):
    """Accept ESPN team-grouped or flat injury lists; reject unknown shapes."""
    groups = payload.get("injuries") if isinstance(payload, dict) else None
    if not isinstance(groups, list):
        return [], False
    candidates = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        # Team groups contain an injuries array; some responses are flat.
        entries = group.get("injuries")
        if not isinstance(entries, list):
            entries = [group] if isinstance(group.get("athlete"), dict) else []
        team = group.get("team") or {}
        if not isinstance(team, dict):
            team = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = get_name(entry)
            if not name:
                continue
            candidates.append({
                "player": name,
                "team": team.get("displayName") or team.get("name"),
                "status": get_status(entry),
            })
    return candidates, True


def review(picks, records, feed_available, fetched_at):
    indexed = {}
    for entry in records:
        indexed.setdefault(norm(entry["player"]), []).append(entry)
    results = []
    for pick in picks:
        matches = indexed.get(norm(pick.get("player")), [])
        # Unknown / absent injury does not mean healthy.
        if not feed_available:
            status = "feed_unavailable"
        elif len(matches) > 1:
            status = "ambiguous_injury_records"
        elif len(matches) == 1:
            status = "reported"
        else:
            status = "not_listed_unconfirmed"
        results.append({
            "player": pick.get("player"),
            "market": pick.get("market"),
            "event": pick.get("event"),
            "reviewStatus": status,
            "reportedInjury": matches[0] if len(matches) == 1 else None,
            "manualAvailabilityCheckRequired": True,
        })
    return {
        "source": "ESPN public NBA injury feed (not official NBA report)",
        "fetchedAt": fetched_at,
        "feedAvailable": feed_available,
        "reportingStatus": "available" if feed_available else "unavailable",
        "recordsParsed": len(records),
        "injuryFeedCostOddsCredits": 0,
        "productionChanges": False,
        "picks": results,
        "note": "ESPN listings can be late or incomplete. Not listed does NOT mean healthy. Confirm official NBA injury report and starting lineups before betting.",
    }


def main():
    now = datetime.now(timezone.utc).isoformat()
    snapshot = json.loads((DOCS / "data.json").read_text())
    records = []
    available = False
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "NBA-EDGE/3.4 research"})
        with urllib.request.urlopen(req, timeout=12) as response:
            payload = json.load(response)
        records, available = extract_injuries(payload)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("ESPN injury feed unavailable; manual review required:", type(exc).__name__)
    report = review(snapshot.get("ranked", []), records, available, now)
    (DOCS / "injury_review.json").write_text(
        json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n")
    print("ESPN injury review:", report["reportingStatus"],
          "flagged:", sum(p["reviewStatus"] == "reported" for p in report["picks"]))


if __name__ == "__main__":
    main()
