"""Research rankings, not calibrated confidence grades or betting recommendations."""
from collections import defaultdict
from zoneinfo import ZoneInfo
from nba_team_model import parse_time

ADVANCED={"NBA":"efficiency_probability","NFL":"epa_probability","NHL":"xg_probability"}

CENTRAL = ZoneInfo("America/Chicago")

def retain_started(snapshot, previous):
    """Carry forward only same-day, genuinely pregame rows and rankings."""
    now = parse_time(snapshot["updated"])
    def started_today(row):
        start = parse_time(row["start"])
        return start <= now and start.astimezone(CENTRAL).date() == now.astimezone(CENTRAL).date()
    for sport, rows in snapshot["sports"].items():
        old_rows = previous.get("sports", {}).get(sport, [])
        frozen = [dict(r, archived_pregame=True) for r in old_rows
                  if started_today(r) and (r.get("archived_pregame") or
                      parse_time(previous["updated"]) < parse_time(r["start"]))]
        snapshot["sports"][sport] = [r for r in rows if parse_time(r["start"]) > now] + frozen
        for market, entries in snapshot["rankings"].get(sport, {}).items():
            old_entries = previous.get("rankings", {}).get(sport, {}).get(market, [])
            frozen_ranks = [dict(r, archived_pregame=True) for r in old_entries
                            if started_today(r) and (r.get("archived_pregame") or
                                parse_time(previous["updated"]) < parse_time(r["start"]))]
            combined = {r["event_id"]: r for r in entries if parse_time(r["start"]) > now}
            combined.update({r["event_id"]: r for r in frozen_ranks})
            snapshot["rankings"][sport][market] = sorted(combined.values(),
                key=lambda r: (r["models"], r["lower_probability"], r["line_gap"], r["odds"]),
                reverse=True)
    return snapshot


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
