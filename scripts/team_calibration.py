"""Fit probability shrinkage on earlier forecasts; evaluate on later dates only."""
from math import log

SCALES=(0.0,.25,.5,.75,1.0,1.25,1.5)

def probabilities(row,scale):
    tie=row.get("tie_probability",0)
    mass=1-tie
    home=min(1,max(0,.5+scale*(row["home_probability"]/mass-.5))) if mass>0 else .5
    return (mass*home,mass*(1-home),tie)

def metrics(rows,scale):
    if not rows:
        return dict(games=0,brier=None,log_loss=None,accuracy=None)
    brier=loss=correct=decisive=0
    for r in rows:
        p=probabilities(r,scale)
        k=("win","loss","push").index(r["actual"])
        brier+=sum((v-(i==k))**2 for i,v in enumerate(p))
        loss-=log(max(1e-12,p[k]))
        if k!=2:
            decisive+=1
            correct+=int((0 if p[0]>=p[1] else 1)==k)
    return dict(games=len(rows),brier=brier/len(rows),log_loss=loss/len(rows),accuracy=correct/decisive if decisive else None)

def evaluate(results):
    rows=sorted(results,key=lambda r:r["time"])
    if len(rows)<60:
        return {"status":"Insufficient sample","games":len(rows)}
    split=rows[int(len(rows)*.6)]["time"][:10]
    train=[r for r in rows if r["time"][:10]<split]
    test=[r for r in rows if r["time"][:10]>=split]
    if len(train)<30 or len(test)<20:
        return {"status":"Insufficient chronological sample","games":len(rows)}
    scale=min(SCALES,key=lambda s:(metrics(train,s)["brier"],abs(s-1)))
    return dict(status="Experimental holdout",scale=scale,split=split,training_games=len(train),
                baseline=metrics(test,1),challenger=metrics(test,scale),coin_flip=metrics(test,0),
                home_only_accuracy=sum(r["actual"]=="win" for r in test)/max(1,sum(r["actual"]!="push" for r in test)))
