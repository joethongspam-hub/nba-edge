"""Separate prospective watchlist and evidence/gap grid; never alters live picks."""
import json
from datetime import timedelta
from ranking_experiment import eligible, normalize, key_for, settle, aggregate

EVIDENCE=(45,50,55,60)
GAPS=(0.60,0.65,0.70,0.75)

def select(rows, now, evidence=50, gap=0.60, excluded=(), limit=5):
    used={(normalize(p['player']),p['startsAt'][:10]) for p in excluded}
    out=[]
    for p in sorted(rows,key=lambda p:(-p['rankingScore'],-p['evidenceScore'],
                    -p['exactNormalizedGap'],normalize(p['player']),p['market'],p['book'])):
        if not eligible(p,now) or p['evidenceScore']<evidence or p['exactNormalizedGap']<gap:
            continue
        key=(normalize(p['player']),p['startsAt'][:10])
        if key in used:continue
        used.add(key)
        out.append(p)
        if len(out)>=limit:break
    return out

def update_file(path, rows, qualified, logs, now, slate):
    try: state=json.loads(path.read_text())
    except (OSError,ValueError):state={'schemaVersion':1,'slates':{}}
    settle(state,logs,now)
    watch=select(rows,now,excluded=qualified)
    groups={'watchlist':watch}
    for e in EVIDENCE:
        for g in GAPS:
            groups[f'e{e}_g{g:.2f}']=select(rows,now,e,g,limit=10)
    if slate not in state['slates'] and any(groups.values()):
        frozen={}
        for items in groups.values():
            for p in items:
                k=key_for(p)
                frozen[k]={**p,'id':k,'result':'pending','selectionRecordedAt':now.isoformat()}
        state['slates'][slate]={'recordedAt':now.isoformat(),
            'groups':{k:[key_for(p) for p in v] for k,v in groups.items()},'picks':frozen}
    cutoff=(now-timedelta(days=365)).date().isoformat()
    state['slates']={k:v for k,v in state['slates'].items() if k>=cutoff}
    path.write_text(json.dumps(state,separators=(',',':'))+'\n')
    reports={k:aggregate([batch['picks'][i] for batch in state['slates'].values()
                       for i in batch['groups'].get(k,[])]) for k in groups}
    return watch, reports
