"""Offline export of existing team forecasts and paper performance."""
import json
from collections import defaultdict
from pathlib import Path
from datetime import timedelta
from nba_team_model import parse_time
from team_benchmark import record

ADVANCED={"NBA":"efficiency_probability","NFL":"epa_probability","NHL":"xg_probability"}

def build(snapshot, tracker):
    now=parse_time(snapshot["updated"])
    sports={}
    for sport, rows in snapshot["sports"].items():
        events=defaultdict(list)
        for row in rows:
            if parse_time(row["start"])<=now:
                continue
            quote={k:row.get(k) for k in ("book","market","team","line","odds","market_probability","model_probability","push_probability","projected_margin","model_status","history_games","shadow_probability",ADVANCED[sport])}
            p=quote["model_probability"]
            m=quote["market_probability"]
            price=quote["odds"]
            quote["model_minus_market_pp"]=round(100*(p-m),3) if p is not None and m is not None else None
            be=(100/(100+price) if price>0 else -price/(100-price)) if price and abs(price)>=100 else None
            quote["break_even_probability_no_push"]=be
            quote["model_minus_break_even_pp"]=round(100*(p-(1-(quote["push_probability"] or 0))*be),3) if p is not None and be is not None else None
            events[(row["event_id"],row["home"],row["away"],row["start"])].append(quote)
        games=[]
        for (event,home,away,start),quotes in sorted(events.items(),key=lambda x:(x[0][3],x[0][0])):
            pairs=defaultdict(list)
            for q in quotes:
                pairs[(q["book"],q["market"])].append(q)
            comparisons=[]
            for (book,market),pair in sorted(pairs.items()):
                if len(pair)!=2 or pair[0]["team"]==pair[1]["team"]:
                    continue
                votes={}
                for field in ("model_probability","shadow_probability",ADVANCED[sport]):
                    a,b=pair
                    if a[field] is not None and b[field] is not None:
                        votes[field]=a["team"] if a[field]>b[field] else b["team"] if b[field]>a[field] else "Tie"
                comparisons.append(dict(book=book,market=market,directions=votes))
            games.append(dict(event_id=event,home=home,away=away,start=start,quotes=quotes,model_directions=comparisons))
        recent=defaultdict(list)
        for r in tracker.get("forecasts",[]):
            if r["sport"]==sport and now-timedelta(days=7)<=parse_time(r["start"])<=now:
                recent[(r["market"],r["book"])].append(r)
        sports[sport]=dict(games=games,rankings=snapshot.get("rankings",{}).get(sport,{}),
            history_health=snapshot.get("history_health",{}).get(sport,{}),
            advanced_health=snapshot.get({"NBA":"nba_efficiency_health","NFL":"nfl_epa_health","NHL":"nhl_xg_health"}[sport],{}),
            recent_seven_day_paper=[dict(market=m,book=b,**record(rs)) for (m,b),rs in sorted(recent.items())],
            lifetime_paper=[r for r in tracker.get("benchmark",[]) if r["sport"]==sport],
            line_movement=[r for r in tracker.get("line_movement",[]) if r["sport"]==sport])
    return dict(schema_version=1,updated=snapshot["updated"],tracker_updated=tracker.get("updated"),
        odds_credits_remaining=snapshot.get("odds_credits_remaining"),
        limitations=["Experimental uncalibrated forecasts; not validated betting recommendations.",
            "Only future games at snapshot generation; includes later dates. Recheck odds and start times.",
            "Margins are not projected final scores; no score totals inferred.",
            "Injuries, confirmed goalies, weather and lineup news require independent verification.",
            "Paper results use archived prices, not real bets. Same games can appear in multiple books and markets.",
            "Latest observed pregame movement is not verified closing-line value.",
            "Missing probabilities are null, not zero. Model agreement is not independent evidence."],sports=sports)

def write(snapshot,tracker,path=Path("docs/team_daily_analysis.json")):
    data=build(snapshot,tracker)
    temp=path.with_suffix(".tmp")
    temp.write_text(json.dumps(data,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    temp.replace(path)
    return data
