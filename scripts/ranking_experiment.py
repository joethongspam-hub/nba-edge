"""Prospective paper-only comparison: EV ranking vs evidence-weighted EV ranking.

Frozen before game start using the same pre-screened props and model values.
Never modifies live Top 10 or historical published bets. No API calls.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import math
from collections import defaultdict
from settlement import unique_verified_log, parse_time
from prop_markets import stat_value

VERSION = 1
MIN_SETTLED_PER_GROUP = 100


def normalize(name):
    return "".join(c for c in str(name).casefold() if c.isalnum())


def eligible(row, now):
    start=parse_time(row.get("startsAt"))
    return start is not None and start > now and row.get("player") and row.get("market")


def risk_score(candidate):
    """Predeclared penalty: estimated EV times squared evidence quality.

    This is a ranking sensitivity experiment, not adjusted win probability or
    a calibrated EV. Do not retrain/tune with the same outcomes being compared.
    """
    evidence=max(0.,min(100.,float(candidate.get("evidenceScore") or 0.)))
    return float(candidate["ev"])*(evidence/100.)**2


def select(candidates, now, mode):
    if mode not in ("ev", "risk"):
        raise ValueError("Unsupported ranking mode")
    filtered=[p for p in candidates if eligible(p,now)]
    metric=(lambda p:float(p["ev"])) if mode=="ev" else risk_score
    ordered=sorted(filtered,key=lambda p:(-metric(p),-float(p["ev"]),normalize(p["player"]),p["market"],p["book"]))
    picked=[];used=set()
    for row in ordered:
        key=(normalize(row["player"]),row["startsAt"][:10])
        if key in used:continue
        picked.append(row)
        used.add(key)
        if len(picked)==10:break
    return picked


def key_for(row):
    return "|".join([row["player"],row["market"],row["side"],
                    str(row["line"]),row["book"],row["startsAt"]])


def freeze(state,candidates,now,slate):
    state.setdefault("schemaVersion",VERSION)
    batches=state.setdefault("slates",{})
    # Never reconstruct old slates from later odds/game information.
    if slate in batches:
        return False
    available=[p for p in candidates if eligible(p,now)]
    if not available:
        return False
    baseline=select(available,now,"ev")
    challenger=select(available,now,"risk")
    # Freeze the full candidate count and both lists at the *same* timestamp.
    frozen={}
    for p in baseline+challenger:
        pk=key_for(p)
        frozen[pk]={
            k:p[k] for k in ("player","market","side","line","book","odds","event",
                            "startsAt","probability","ev","edge","grade","evidenceScore")
            if k in p
        }
        frozen[pk].update({"result":"pending","id":pk,"selectionRecordedAt":now.isoformat(),
                           "riskScore":round(risk_score(p),5)})
        if p.get("oddsEventId"):
            frozen[pk]["oddsEventId"]=p["oddsEventId"]
    batches[slate]={"recordedAt":now.isoformat(),"candidateCount":len(available),
                    "ev":[key_for(x) for x in baseline],
                    "risk":[key_for(x) for x in challenger],
                    "picks":frozen}
    return True


def settle(state,logs,now):
    grouped=defaultdict(list)
    for g in logs:
        if g.get("player"):
            grouped[normalize(g["player"])].append(g)
    changed=0
    for batch in state.get("slates",{}).values():
        for p in batch.get("picks",{}).values():
            if p.get("result")!="pending":continue
            start=parse_time(p.get("startsAt"))
            if start is None or now < start+timedelta(hours=4):
                continue
            matching=unique_verified_log(p,grouped[normalize(p.get("player"))])
            if matching is None:
                p["settlementStatus"]="awaiting_verified_game"
                continue
            actual=stat_value(matching,p["market"])
            if actual is None:
                p["settlementStatus"]="awaiting_verified_stat"
                continue
            win=(actual>p["line"]) if p["side"]=="Over" else (actual<p["line"])
            result="push" if actual==p["line"] else ("win" if win else "loss")
            odds=float(p["odds"])
            if odds == 0 or not math.isfinite(odds):
                p["settlementStatus"]="invalid_odds"
                continue
            p.update({"actual":actual,"result":result,"settledAt":now.isoformat(),
                      "settlementStatus":"verified_matchup_and_start",
                      "verifiedGameId":matching["gameId"],
                      "units":round((odds/100 if odds>0 else 100/-odds) if win else
                                    (0 if result=="push" else -1),4)})
            changed+=1
    return changed


def aggregate(rows):
    wins=sum(p["result"]=="win" for p in rows)
    losses=sum(p["result"]=="loss" for p in rows)
    pushes=sum(p["result"]=="push" for p in rows)
    units=sum(p.get("units",0) for p in rows if p["result"] in ("win","loss","push"))
    n=wins+losses
    return {"selections":len(rows),"wins":wins,"losses":losses,"pushes":pushes,
            "pending":sum(p["result"]=="pending" for p in rows),
            "roi":round(units/n,4) if n else None,
            "winRate":round(wins/n,4) if n else None,
            "units":round(units,3),"graded":n,
            "meanEvidence":round(sum(float(x.get("evidenceScore",0)) for x in rows)/len(rows),1) if rows else None}


def report(state):
    batches=state.get("slates",{})
    lists={"ev":[],"risk":[]}
    overlaps=0
    paired_dates=0
    for batch in batches.values():
        entries=batch.get("picks",{})
        ev=batch.get("ev",[])
        risk=batch.get("risk",[])
        if ev and risk:
            paired_dates+=1
            overlaps+=len(set(ev)&set(risk))
        for name,keys in (("ev",ev),("risk",risk)):
            lists[name].extend(entries[k] for k in keys if k in entries)
    summary={k:aggregate(v) for k,v in lists.items()}
    ready=min(summary["ev"]["graded"],summary["risk"]["graded"])>=MIN_SETTLED_PER_GROUP
    return {"status":"prospective_paper_experiment",
            "productionChanges":False,"usesExtraOddsRequests":False,
            "rankingMethods":{"ev":"Highest raw estimated EV, one prop per player/date",
                              "risk":"Estimated EV * (evidenceScore/100)^2; one prop per player/date"},
            "slatesCompared":paired_dates,"overlappingSelections":overlaps,
            "results":summary,"minimumSettledSelectionsPerGroup":MIN_SETTLED_PER_GROUP,
            "sufficientForReview":ready,
            "note":"Both lists share the same pregame eligible candidate set and frozen prices. Overlapping selections are not independent bets. ROI is paper return using archived odds; small samples and uncertain probabilities cannot establish a profitable strategy. No past rankings are reconstructed."}


def update_file(path,candidates,logs,now,slate):
    path=Path(path)
    try:
        state=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError):
        state={"schemaVersion":VERSION,"slates":{}}
    settle(state,logs,now)
    freeze(state,candidates,now,slate)
    cutoff=(now-timedelta(days=365)).date().isoformat()
    state["slates"]={k:v for k,v in state["slates"].items() if k>=cutoff}
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(state,separators=(",",":"),ensure_ascii=False)+"\n",encoding="utf-8")
    return report(state)
