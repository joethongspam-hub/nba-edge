#!/usr/bin/env python3
"""Resumable, ESPN-only historical boxscore context backfill for NBA EDGE.

No Odds API calls; never changes historical stat totals or settlement outcomes.
Runs in bounded batches and keeps an attempted-game ledger to avoid refetching
successfully processed game IDs with unavailable positions.
"""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path

from context_research import _clean_opponent, _position
from settlement import team_name, matchup_from_string
from update import ROOT, boxscore

CONTEXT_VERSION = 1
MAX_ATTEMPTS = 3
DEFAULT_BATCH = 48
MAX_BATCH = 120


def matched_side(event, reported_team):
    """Match team identity to saved scoreboard matchup, including known aliases."""
    if not isinstance(event, str) or " @ " not in event or not reported_team:
        return None
    away, home = event.split(" @ ", 1)
    a, h, t = team_name(away), team_name(home), team_name(reported_team)
    if not a or not h or a == h:
        return None
    if t == a:
        return away, home
    if t == h:
        return home, away
    return None


def needs_context(row):
    return not (_clean_opponent(row) and _position(row))


def candidate_game_ids(data, limit=DEFAULT_BATCH):
    attempts = data.get("contextBackfill") or {}
    completed = set(attempts.get("attemptedGameIds") or [])
    failures = attempts.get("failedGames") or {}
    groups = defaultdict(list)
    for row in data.get("logs", []):
        if row.get("gameId") and row.get("playerId") and row.get("date"):
            groups[str(row["gameId"])].append(row)
    pending = [gid for gid, rows in groups.items()
               if gid not in completed and failures.get(gid, 0) < MAX_ATTEMPTS
               and any(needs_context(r) for r in rows)]
    pending.sort(key=lambda gid: (min(r["date"] for r in groups[gid]), gid))
    return pending[:limit], len(pending)


def merge_game_context(data, game_id, refreshed):
    """Merge *only* identity/context; never overwrite score or minutes."""
    by_id = {str(r.get("playerId")): r for r in refreshed
             if r.get("playerId") and str(r.get("gameId")) == game_id}
    updated = 0
    for old in data.get("logs", []):
        if str(old.get("gameId")) != game_id:
            continue
        new = by_id.get(str(old.get("playerId")))
        if not new:
            continue
        before = {k: old.get(k) for k in
                  ("event","startsAt","team","teamId","position","opponent")}
        # Never use a new summary if it contradicts a previously matched
        # scoreboard. Only the same identified player/game may be enriched.
        old_matchup=matchup_from_string(old.get("event"))
        new_matchup=matchup_from_string(new.get("event"))
        if old_matchup and new_matchup and old_matchup != new_matchup:
            continue
        if not old_matchup and new_matchup:
            old["event"]=new["event"]
            if new.get("startsAt") and not old.get("startsAt"):
                old["startsAt"]=new["startsAt"]
        matched = matched_side(old.get("event"), new.get("team"))
        if matched:
            old["team"], old["opponent"] = matched
            if new.get("teamId"):
                old["teamId"] = str(new["teamId"])
        position = new.get("position")
        if isinstance(position, str) and position.upper() in ("PG","SG","SF","PF","C"):
            old["position"] = position.upper()
        if any(old.get(k) != before[k] for k in before):
            updated += 1
    return updated


def backfill(data, fetcher=boxscore, limit=DEFAULT_BATCH, workers=3):
    if not (1 <= limit <= MAX_BATCH):
        raise ValueError("Batch limit must be between 1 and 120")
    selected, remaining_before = candidate_game_ids(data, limit)
    if not selected:
        # Do not commit a changing timestamp forever after the backlog is done.
        state = data.get("contextBackfill") or {}
        return {"selectedGames":0,"successfulGames":0,"updatedRows":0,
                "contextQualifiedRows":sum(not needs_context(r) for r in data.get("logs",[])),
                "remainingUnattemptedGames":remaining_before,
                "permanentlyFailedGames":sum(v>=MAX_ATTEMPTS for v in
                                              (state.get("failedGames") or {}).values()),
                "noOddsApiRequests":True}
    state = data.setdefault("contextBackfill", {})
    if state.get("version") not in (None, CONTEXT_VERSION):
        raise ValueError("Unsupported contextBackfill state version")
    completed = set(state.get("attemptedGameIds") or [])
    failures = dict(state.get("failedGames") or {})
    game_dates = {}
    for row in data.get("logs", []):
        if str(row.get("gameId")) in selected:
            game_dates.setdefault(str(row["gameId"]), row["date"])
    successes = 0
    updated = 0

    def fetch_one(game_id):
        return fetcher(game_id, game_dates[game_id])

    # Small concurrency only against public ESPN summary endpoints, not odds.
    if selected:
        with ThreadPoolExecutor(max_workers=max(1,min(workers,4))) as pool:
            futures={pool.submit(fetch_one,gid):gid for gid in selected}
            for future in as_completed(futures):
                gid=futures[future]
                try:
                    rows=future.result()
                    if not isinstance(rows,list) or not rows:
                        raise ValueError("Empty ESPN boxscore; will retry")
                    updated += merge_game_context(data,gid,rows)
                    completed.add(gid)
                    failures.pop(gid,None)
                    successes += 1
                except Exception as exc:
                    failures[gid]=failures.get(gid,0)+1
                    print(f"ESPN context backfill warning: {gid}: {type(exc).__name__}: {exc}")
    existing_ids={str(r.get("gameId")) for r in data.get("logs",[]) if r.get("gameId")}
    state.update({
        "version": CONTEXT_VERSION,
        "attemptedGameIds": sorted(completed & existing_ids),
        "failedGames": {k:v for k,v in sorted(failures.items()) if k in existing_ids},
        "lastRunAt":datetime.now(timezone.utc).isoformat(),
    })
    remaining_after = candidate_game_ids(data, MAX_BATCH)[1]
    eligible = sum(not needs_context(r) for r in data.get("logs",[]))
    summary = {"selectedGames":len(selected),"successfulGames":successes,
               "updatedRows":updated,"contextQualifiedRows":eligible,
               "remainingUnattemptedGames":remaining_after,
               "permanentlyFailedGames":sum(v>=MAX_ATTEMPTS for v in failures.values()),
               "noOddsApiRequests":True}
    state["lastRun"] = summary
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit",type=int,default=DEFAULT_BATCH)
    args=parser.parse_args()
    path=Path(ROOT)/"game_logs.json"
    data=json.loads(path.read_text(encoding="utf-8"))
    summary=backfill(data,limit=args.limit)
    temp=path.with_name(path.name+".tmp")
    temp.write_text(json.dumps(data,separators=(",",":"),ensure_ascii=False)+"\n",encoding="utf-8")
    temp.replace(path)
    print("ESPN context backfill:",json.dumps(summary,sort_keys=True))


if __name__=="__main__":
    main()
