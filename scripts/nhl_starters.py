"""Research-only starting goalie context; no Odds API calls."""
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import re
from nhl_efficiency import NAMES
from nba_team_model import parse_time

BASE = "https://www.dailyfaceoff.com/starting-goalies/"
STATUS = {"confirmed": "confirmed", "unconfirmed": "projected",
          "projected": "projected", "probable": "projected", "expected": "projected",
          "unknown": "unknown"}
def norm(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())

class Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.hidden += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.hidden = max(0, self.hidden-1)
    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(" ".join(data.split()))

def parse(html, source, now, diagnostics=None):
    parser = Visible()
    parser.feed(html)
    # Match explicit team names, game time, then exactly two explicit
    # status labels. Ambiguous cards are deliberately not mapped.
    names = {norm(n): n for n in NAMES.values()}
    names[norm("St Louis Blues")] = "St. Louis Blues"
    headings = []
    i = 0
    while i < len(parser.parts):
        found = False
        for width in range(1, min(12, len(parser.parts)-i)+1):
            text = " ".join(parser.parts[i:i+width])
            bits = re.split(r"\s+at\s+", text, flags=re.I)
            if len(bits) == 2 and all(norm(b) in names for b in bits):
                headings.append((i, i+width, names[norm(bits[0])], names[norm(bits[1])]))
                i += width
                found = True
                break
        if not found:
            i += 1
    if diagnostics is not None:
        diagnostics.update(text_nodes=len(parser.parts), headings=len(headings),
                           status_nodes=sum(p.lower() in STATUS for p in parser.parts),
                           iso_nodes=sum(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\S+", p))
                                         for p in parser.parts),
                           sample=parser.parts[:50])
    results = {}
    for j, (i, after, away, home) in enumerate(headings):
        end = headings[j+1][0] if j+1 < len(headings) else len(parser.parts)
        parts = parser.parts[after:end]
        if not parts:
            continue
        timestamps = [p for p in parts[:8] if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\S+", p)]
        if not timestamps:
            continue
        try:
            start = parse_time(timestamps[0])
        except (ValueError, TypeError):
            continue
        if start <= now:
            continue
        pairs = []
        for k, part in enumerate(parts):
            status = STATUS.get(part.lower())
            if status is None or k < 2:
                continue
            name = parts[k-1]
            if not (2 <= len(name.split()) <= 5 and
                    all(c.isalpha() or c in " .-'’" for c in name)):
                continue
            reported = None
            if k+1 < len(parts):
                try:
                    reported = parse_time(parts[k+1])
                except (ValueError, TypeError):
                    pass
            # Confirmation must have an explicit pregame timestamp.
            if status == "confirmed" and (reported is None or reported > now):
                status = "unknown"
            pairs.append({"name": name if status != "unknown" else None,
                          "status": status, "source": source,
                          "reported_at": reported.isoformat() if reported and reported <= now else None,
                          "checked_at": now.isoformat()})
        if len(pairs) == 2:
            key = (norm(home), norm(away), start)
            if key in results:
                results[key] = None
            else:
                results[key] = {"away": pairs[0], "home": pairs[1]}
    return {k:v for k,v in results.items() if v is not None}

def annotate(rows, now):
    dates = {parse_time(r["start"]).astimezone(ZoneInfo("America/New_York")).date()
             for r in rows if now < parse_time(r["start"]) <= now + timedelta(hours=36)}
    entries, errors, diagnostics = {}, [], {}
    for day in sorted(dates):
        source = BASE + day.isoformat()
        try:
            with urlopen(Request(source, headers={"User-Agent": "Sports Edge research"}), timeout=15) as response:
                raw = response.read(8000000)
                detail = {"bytes": len(raw), "url": response.geturl()}
                diagnostics[day.isoformat()] = detail
                parsed = parse(raw.decode("utf-8"), source, now, detail)
                detail["matched_cards"] = len(parsed)
            if not parsed:
                errors.append(day.isoformat()+": no recognized future cards")
            entries.update(parsed)
        except Exception as exc:
            errors.append(day.isoformat()+": "+type(exc).__name__)
    matched = set()
    for row in rows:
        start = parse_time(row["start"])
        key = (norm(row["home"]), norm(row["away"]), start)
        # Books sometimes publish slightly different start times. Require
        # same teams and a unique source matchup within 15 minutes.
        candidates = [v for k,v in entries.items() if k[:2] == key[:2]
                      and abs((k[2]-start).total_seconds()) <= 900]
        pair = candidates[0] if len(candidates) == 1 and start > now else {}
        for side in ("home", "away"):
            row["goalie_"+side] = pair.get(side, {"name": None, "status": "unknown",
                "source": None, "reported_at": None, "checked_at": now.isoformat()})
        if pair:
            matched.add(key)
    return {"source": BASE, "checked_at": now.isoformat(), "matched_games": len(matched),
            "eligible_games": len({(r["home"],r["away"],r["start"]) for r in rows
                                   if now < parse_time(r["start"]) <= now+timedelta(hours=36)}),
            "errors": errors, "diagnostics": diagnostics, "research_only": True}
