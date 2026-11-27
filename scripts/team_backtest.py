"""Walk-forward moneyline audit; no historical sportsbook prices assumed."""
from datetime import timedelta
import nba_team_model
import nfl_team_model
import nhl_team_model

MODELS={"NBA":(nba_team_model,84),"NFL":(nfl_team_model,126),"NHL":(nhl_team_model,84)}

def evaluate(sport,games):
    model,lookback=MODELS[sport]
    results=[]
    for game in sorted(games,key=lambda g:g[0]):
        time,home,away=game[:3]
        # Whole previous UTC days only: avoids using same-day games not yet final.
        cutoff=time.replace(hour=0,minute=0,second=0,microsecond=0)
        train=[g for g in games if cutoff-timedelta(days=lookback)<=g[0]<cutoff]
        rows=[dict(home=home,away=away,team=t,market="h2h",line=None) for t in (home,away)]
        model.annotate(rows,train,cutoff)
        if any("model_probability" not in r for r in rows):
            continue
        r=rows[0]
        margin=game[3]-game[4] if sport=="NHL" else game[3]
        actual="win" if margin>0 else "loss" if margin<0 else "push"
        p=r["model_probability"]; q=r.get("push_probability",0)
        loss=max(0,1-p-q)
        chosen="win" if p>=loss else "loss"
        brier=sum((prob-(actual==label))**2 for label,prob in (("win",p),("loss",loss),("push",q)))
        results.append(dict(time=time.isoformat(),home=home,away=away,home_probability=p,tie_probability=q,actual=actual,correct=chosen==actual,brier=brier,margin_error=abs(r["projected_margin"]-margin)))
    n=len(results)
    decisive=[r for r in results if r["actual"]!="push"]
    buckets=[]
    for low,high in [(0,.5),(.5,.6),(.6,.7),(.7,.8),(.8,1.01)]:
        subset=[r for r in results if low<=r["home_probability"]<high]
        if subset:
            buckets.append(dict(low=low,high=min(high,1),n=len(subset),predicted=sum(r["home_probability"] for r in subset)/len(subset),observed=sum(r["actual"]=="win" for r in subset)/len(subset)))
    return dict(sport=sport,games=n,available_games=len(games),decisive=len(decisive),accuracy=sum(r["correct"] for r in decisive)/len(decisive) if decisive else None,brier=sum(r["brier"] for r in results)/n if n else None,margin_mae=sum(r["margin_error"] for r in results)/n if n else None,calibration=buckets,results=results)

def audit(histories):
    return [evaluate(sport,games) for sport,games in histories.items() if sport in MODELS]
