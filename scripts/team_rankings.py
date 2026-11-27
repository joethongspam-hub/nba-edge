"""Research rankings, not calibrated confidence grades or betting recommendations."""
from collections import defaultdict
from nba_team_model import parse_time

ADVANCED={"NBA":"efficiency_probability","NFL":"epa_probability","NHL":"xg_probability"}

def rankings(snapshot):
    now=parse_time(snapshot["updated"])
    output={}
    for sport,rows in snapshot["sports"].items():
        groups=defaultdict(list)
        for row in rows:
            if parse_time(row["start"])>now and row.get("model_probability") is not None:
                groups[(row["event_id"],row["market"],row["book"])].append(row)
        best={}
        for (_,market,_),pair in groups.items():
            if len(pair)!=2 or pair[0]["team"]==pair[1]["team"]:continue
            r=max(pair,key=lambda x:x["model_probability"])
            other=next(x for x in pair if x is not r)
            fields=("model_probability","shadow_probability",ADVANCED[sport])
            available=[k for k in fields if r.get(k) is not None and other.get(k) is not None]
            votes=sum(r[k]>other[k] for k in available)
            if len(available)<2 or votes!=len(available):continue
            # Conservative lower probability across agreeing models. Not a
            # validated probability or evidence of an edge over the price.
            lower=min(r[k] for k in available)
            gap=lower-.5
            if gap<=0:continue
            entry={k:r.get(k) for k in ("event_id","market","book","home","away","team","start","line","odds","projected_margin","model_probability","market_probability")}
            entry.update(models=len(available),agreement=votes,lower_probability=round(lower,6),
                         probability_range=[round(lower,6),round(max(r[k] for k in available),6)],
                         line_gap=round(r["projected_margin"]+(r.get("line") or 0),2))
            key=(r["event_id"],market)
            order=(len(available),lower,entry["line_gap"],r["odds"])
            if key not in best or order>best[key][0]:best[key]=(order,entry)
        output[sport]={market:[v[1] for v in sorted(best.values(),key=lambda v:v[0],reverse=True) if v[1]["market"]==market][:10] for market in ("h2h","spreads")}
    return output
