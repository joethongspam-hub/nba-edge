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
the historical tracker matches by player/date rather than guaranteed event ID.
The exporter intentionally leaves probabilities and grades unchanged and sets
`sufficientForCalibration` to false. A follow-up version should save stable event
identifiers on each pick, validate settlement, collect larger out-of-sample
histories, and only then fit and evaluate probability calibrators with
chronological holdouts.

To reproduce without network usage:

```sh
python scripts/analysis_export.py
python -m unittest discover -s tests -v
```
