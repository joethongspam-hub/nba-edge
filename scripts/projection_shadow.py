"""Prospective paper-only projection-discrepancy ranking, independent of EV.

Frozen selections and sportsbook prices are never rewritten; game outcomes
are verified by the existing player/matchup/start-time ESPN matcher.
"""
import json
from datetime import timedelta
from pathlib import Path
from ranking_experiment import (eligible, key_for, normalize, settle, aggregate)

MIN_SETTLED=100

def select(rows,now):
    """No EV or arbitrary evidence-60 gate. Research screen, not assured picks."""
    pool=[p for p in rows if eligible(p,now)]
    pool.sort(key=lambda p:(-p["paperRankingScore"],-p["normalizedGap"],
                             -p["evidenceScore"],normalize(p["player"]),
                             p["market"],p["book"]))
    top=[];used=set()
    for row in pool:
        player_day=(normalize(row["player"]),row["startsAt"][:10])
        if player_day in used:continue
        used.add(player_day)
        top.append(row)
        if len(top)==10:break
    return top

def freeze(state,rows,now,slate):
    state.setdefault("schemaVersion",1)
    slates=state.setdefault("slates",{})
    if slate in slates:return False
    available=[p for p in rows if eligible(p,now)]
    if not available:return False
    selected=select(available,now)
    records={}
    for row in selected:
        identity=key_for(row)
        fields=("player","market","side","line","book","odds","event",
                "startsAt","projection","volatility","normalizedGap",
                "projectionGap","sample","evidenceScore","paperRankingScore",
                "paperEvidenceLabel","historyOlderThan90Days")
        records[identity]={k:row[k] for k in fields if k in row}
        records[identity].update({"id":identity,"selectionRecordedAt":now.isoformat(),
                                   "result":"pending"})
        if row.get("oddsEventId"):records[identity]["oddsEventId"]=row["oddsEventId"]
    slates[slate]={"recordedAt":now.isoformat(),"eligibleProps":len(available),
                   "selected":[key_for(row) for row in selected],
                   "picks":records}
    return True

def report(state):
    rows=[]
    for slate in state.get("slates",{}).values():
        rows.extend(slate.get("picks",{}).get(k) for k in slate.get("selected",[])
                    if k in slate.get("picks",{}))
    results=aggregate(rows)
    return {"status":"prospective_projection_gap_shadow",
            "productionChanges":False,"extraOddsApiCalls":0,
            "slatesRecorded":len(state.get("slates",{})),
            "minimumSettledForReview":MIN_SETTLED,
            "sufficientForReview":results["graded"]>=MIN_SETTLED,
            "results":results,
            "latest":next(({"slate":day,
                             "eligibleProps":batch["eligibleProps"],
                             "selections":[batch["picks"][k] for k in batch["selected"]]}
                             for day,batch in sorted(state.get("slates",{}).items(),reverse=True)
                             if batch.get("selected")),None),
            "note":"Research-only pregame selections. Score = standardized directional stat gap * (0.5 + evidence/200); 15+ usable history games, <=20 old games, correct gap >=0.5 and >=0.75 std. No EV sorting or evidence >=60 cutoff. Label reflects historical evidence only, not a calibrated win probability. Results settle only from uniquely verified ESPN game logs. Shared markets/players, data-quality differences and predeclared thresholds limit inference."}

def update_file(path,rows,logs,now,slate):
    path=Path(path)
    try:state=json.loads(path.read_text())
    except (OSError,ValueError):state={"schemaVersion":1,"slates":{}}
    settle(state,logs,now)
    freeze(state,rows,now,slate)
    cutoff=(now-timedelta(days=365)).date().isoformat()
    state["slates"]={k:v for k,v in state["slates"].items() if k>=cutoff}
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(state,separators=(",",":"),ensure_ascii=False)+"\n")
    return report(state)
