"""Prospective paper-only normalized-gap threshold comparison.

Same frozen candidate pool, rankings and pregame lines at .60/.65/.70/.75.
No sportsbook requests, no production ranking changes, no historical backfill.
"""
import json
from datetime import timedelta
from pathlib import Path
from ranking_experiment import eligible, key_for, normalize, settle, aggregate

THRESHOLDS=(0.60,0.65,0.70,0.75)
MIN_GRADED=100

def select(candidates,now,threshold):
    pool=[p for p in candidates if eligible(p,now)
          and float(p["normalizedGap"])>=threshold]
    pool.sort(key=lambda p:(-p["paperRankingScore"],-p["normalizedGap"],
                 -p["evidenceScore"],normalize(p["player"]),p["market"],p["book"]))
    result=[];used=set()
    for row in pool:
        key=(normalize(row["player"]),row["startsAt"][:10])
        if key in used:continue
        used.add(key)
        result.append(row)
        if len(result)>=10:break
    return result

def freeze(state,candidates,now,slate):
    state.setdefault("schemaVersion",1)
    slates=state.setdefault("slates",{})
    if slate in slates:return False
    available=[p for p in candidates if eligible(p,now)]
    if not available:return False
    selections={f"{t:.2f}":select(available,now,t) for t in THRESHOLDS}
    frozen={}
    for rows in selections.values():
        for row in rows:
            k=key_for(row)
            if k in frozen:continue
            fields=("player","market","side","line","book","odds","event",
                    "startsAt","projection","volatility","normalizedGap",
                    "projectionGap","sample","evidenceScore","paperRankingScore",
                    "paperEvidenceLabel","historyOlderThan90Days","oddsEventId")
            frozen[k]={field:row[field] for field in fields if field in row}
            frozen[k].update({"id":k,"selectionRecordedAt":now.isoformat(),
                              "result":"pending"})
    slates[slate]={"recordedAt":now.isoformat(),
                   "candidateCount":len(available),
                   "groups":{k:[key_for(p) for p in v] for k,v in selections.items()},
                   "picks":frozen}
    return True

def report(state):
    slates=state.get("slates",{})
    grouped={f"{t:.2f}":[] for t in THRESHOLDS}
    overlaps={}
    for slate in slates.values():
        picks=slate.get("picks",{})
        groups=slate.get("groups",{})
        for threshold,rows in grouped.items():
            rows.extend(picks[k] for k in groups.get(threshold,[]) if k in picks)
    for threshold in ("0.60","0.65","0.70"):
        overlaps[threshold]=sum(len(set(s.get("groups",{}).get(threshold,[])) &
                                  set(s.get("groups",{}).get("0.75",[])))
                                for s in slates.values())
    summaries={k:aggregate(v) for k,v in grouped.items()}
    return {"status":"prospective_normalized_gap_paper_comparison",
            "thresholds":[f"{t:.2f}" for t in THRESHOLDS],
            "productionChanges":False,"extraOddsApiCalls":0,
            "slatesRecorded":len(slates),"results":summaries,
            "overlapWithBaseline":overlaps,
            "minimumGradedPerThreshold":MIN_GRADED,
            "sufficientForReview":all(v["graded"]>=MIN_GRADED for v in summaries.values()),
            "note":"Identical pregame candidate pools, ranking weights, evidence eligibility and frozen odds; thresholds differ only by normalized gap. One player per game date, top 10 per group. Overlap is not independent data. No historical sportsbook lines reconstructed. Review later out-of-sample dates before any production change."}

def update_file(path,candidates,logs,now,slate):
    path=Path(path)
    try:state=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError):state={"schemaVersion":1,"slates":{}}
    settle(state,logs,now)
    freeze(state,candidates,now,slate)
    cutoff=(now-timedelta(days=365)).date().isoformat()
    state["slates"]={k:v for k,v in state["slates"].items() if k>=cutoff}
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(state,separators=(",",":"),ensure_ascii=False)+"\n",encoding="utf-8")
    return report(state)
