# NBA EDGE daily analysis and calibration diagnostics

Each completed scheduled refresh runs `scripts/analysis_export.py` using already-published
`docs/data.json` and `docs/tracker.json`. **No Odds API requests** are made by this exporter.

## ChatGPT-ready export

The published JSON is at:
`https://joethongspam-hub.github.io/nba-edge/daily_analysis.json`

It includes the current ranked picks and their odds, slate/snapshot timestamps,
overall and per-market outcome diagnostics, plus an injury/odds validation checklist.

Suggested ChatGPT prompt:

> Review this NBA EDGE daily analysis JSON. Check snapshot and odds freshness,
> current NBA injury/lineup news, and live price changes. Treat model probabilities
> as uncalibrated. Identify missing information, correlated picks, and potential
> false positives. Present a shortlist only where independently verified evidence
> supports it; otherwise recommend no bet.

## Metrics and interpretation

- `graded`: settled wins + losses; pushes excluded.
- `roi`: sum of one-unit returns divided by graded bets with valid odds.
- `brierScore`: mean squared error of stated win probabilities vs outcomes.
- `logLoss`: average negative log likelihood; lower is better.
- `calibrationBuckets`: predicted vs observed win rate by 10-point probability bins.
- `byMarket`: diagnostics split by prop market.

**Do not interpret these results as out-of-sample calibration.** The current
sample is small, picks are selected by the same model being evaluated, and
historical legacy outcomes were settled by player/date without guaranteed event identity.
The exporter intentionally leaves probabilities and grades unchanged and sets
`sufficientForCalibration` to false. New settlements use matchup/time verification; a future version should audit older legacy outcomes, collect larger out-of-sample histories, and only then fit probability calibrators with chronological holdouts.

To reproduce without network usage:

```sh
python scripts/analysis_export.py
python -m unittest discover -s tests -v
```

## Verified settlement (Upgrade 2)

New sportsbook picks save `oddsEventId` for traceability. ESPN boxscore rows
include an ESPN `gameId`, matchup and scheduled start time. A pending pick
is settled only if the player's unique boxscore row has a matching away/home
matchup and a start time within 18 hours of the sportsbook event. Otherwise
it remains pending with `settlementStatus=awaiting_verified_game`.

Successful matches record `verifiedGameId`, `verifiedPlayerId`,
`verifiedGameStart` and `settlementStatus=verified_matchup_and_start`.
This is cross-provider evidence, not direct equality of vendor event IDs.

The ChatGPT export now separates `calibration.verifiedOnly` from
`calibration.legacyUnverified`, retaining the historical overall figures.
Previously settled picks are NOT silently rewritten or called verified.
Review legacy figures separately until manually audited.

This upgrade uses the ESPN scoreboard and boxscore endpoints already queried
during historical refresh. It makes no additional Odds API requests.

## Upgrade 3: walk-forward calibration readiness

The daily JSON now includes `walkForwardBacktest` for verified outcomes.
It groups by frozen slate date and fits a simple probability shrinkage
weight using **only earlier slate dates**. Historical same-day picks never
train each other. It compares the original model with an experimental
shrinkage-to-50%-baseline diagnostic, scored by Brier error on later slates.

Each overall/market backtest requires at least 100 earlier verified
win/loss predictions before evaluating a slate, plus at least 30 evaluated
picks before publishing diagnostic scores. Legacy or incomplete/invalid
records do not count. Missing data returns
`status=insufficient_verified_history` and null diagnostic scores.

**No production calibration is enabled.** The existing model probability,
EV calculation, filtering, A/B/C grades, odds selection, and 5:13 PM Central
schedule are unchanged. This small experimental benchmark does not establish
betting profitability or overcome selection bias. A future upgrade can
evaluate multiple model families and tune thresholds on independent, more
numerous prospective samples.
