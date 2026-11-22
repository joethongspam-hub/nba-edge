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

## Upgrade 4: shadow role-and-minutes projection research

`shadowProjectionResearch` is built from existing ESPN game logs after
each run, without Odds API requests. It predicts projected minutes from
recent and longer trends and a winsorized per-minute production rate.
For each current ranked prop it exports `shadowProjection`, sample size,
role-change percentage, and warnings such as unstable playing time.

The `historicalStatError` section uses strictly earlier dates for each
completed game, comparing shadow-projection MAE/RMSE against a simple
weighted-average stat baseline. This is a **stat-error** replay, not a
backtest of betting edges or model probability calibration. Same-date
games do not train predictions for one another.

**Shadow mode only:** it does not alter live rankings, EV, probability
estimates, or grade thresholds. Injury feed and opponent adjustment
are explicitly marked disconnected. Projected minutes are heuristic
and can be wrong after injuries, trades or rotation changes. Do not
interpret a lower historical MAE as profitable betting evidence.

## Upgrade 5: free ESPN injury review + Odds API quota reserve

The daily refresh adds `docs/injury_review.json` from the public ESPN NBA
injury endpoint. Entries are also included as `injuryReview` in the
ChatGPT-ready daily report. A matching listed injury is **not** an official
game-day designation, and a player *not listed* is **not** necessarily healthy.
Unavailable or malformed feeds result in explicit unavailable flags.
Every pick requires independent official injury/lineup confirmation.

This is shadow-only. NBA EDGE does not change the production projections,
probabilities, rankings, or grades based on ESPN injury feed results.

### Live credit guard

Before any paid odds call, the updater reads `x-requests-remaining`
from a free Odds API event-listing call. It reserves 2,000 credits plus a
conservative **8 credits per remaining game** (4 player markets with US
bookmakers). If the live response lacks the quota header or cannot cover
**every scheduled game**, it **aborts the odds refresh** and sends a failure
notification rather than paying for a partial slate or running below the
reserve. It checks the remaining quota again before each paid game query.

This guard has no new paid quota calls and preserves every game and market
when budget permits. Credit counts are from the actual API headers, not the
historical cached balance. External tools using the same API key concurrently
could affect the balance, and an unexpectedly priced API query could still
use more credits than predicted; do not treat the guard as a mathematically
absolute spending guarantee.

Same-day cached reruns skip the paid odds path entirely. If a new day's
quota is insufficient, the workflow intentionally fails closed and leaves
the previous published snapshot intact.

## Upgrade 7: outcome audit, direction bias and frozen projection tracking

The scheduled export now includes:

- `calibration.bySide`, `byGrade`, `bySlate`, and `byMarketAndSide` for
  wins, losses, ROI, mean stated hit probability, and Brier score.
- `settlementAudit`: a read-only comparison of **all settled picks** with
  unique game logs matching player name, matchup and start time. Older legacy
  outcomes may be `legacy_corroborated` retrospectively, but **are not**
  promoted to the `verified_matchup_and_start` training subset. Missing,
  mismatched and ambiguous cases require manual review. Existing recorded
  outcomes are never changed.
- `historicalPickProjectionReplay`: reconstructed minutes-aware shadow stat
  estimates using logs with dates **strictly before the saved slate date**.
  Its MAE and directional mean error are not original pregame forecasts and
  cannot prove profitable odds.
- `frozenProjectionAccuracy`: for **new** tracked picks, the screen saves the
  selected pregame model projection and supporting sample/evidence fields in
  `docs/tracker.json`. Once those picks settle, their original frozen
  projections can be compared with actual stats. Older picks without these
  fields are excluded, not guessed.

The GitHub Pages dashboard now shows per-market and Over/Under performance and
settlement-audit warnings. These diagnostics require only ESPN history and
local snapshots and **do not issue additional Odds API queries**.

No grade A promotion, probability recalibration, automatic market suppression,
injury-based adjustment, or live EV threshold change is introduced here.
Current samples are too small to justify such tuning; use prospective verified
records and out-of-sample evaluation before changing production picks.

The live quota guard now allows for **eight** player markets, reserving 2,000
credits and preflighting a conservative 12 credits per game, rather than the
previous four-market estimate documented above.

## Upgrade 18A: same-game NBA EDGE vs Claude-inspired model comparison

Each daily `scripts/analysis_export.py` run now publishes `modelHeadToHead`.
No additional API requests or changed production rankings are involved.

For each player and completed date, both models use **exactly the same ESPN
historical game logs dated strictly before that date**. All 8 player prop
markets (including derived combination stats) are included:

- **NBA EDGE**: the existing production model's recency-weighted (0.97) mean
  statistic from up to 40 eligible games, using only games with 12+ minutes.
- **Claude-inspired core**: a reproduction of the NBA-Picks model's core
  blended per-minute current/previous-season and last-10 production rates,
  multiplied by projected minutes from the last five games and season history.

This is **not** the complete Claude NBA-Picks model: opponent defense by
position, injury effects, Vegas team totals, rest and probability blending
cannot be reproduced faithfully from NBA EDGE's current game-log fields.
The benchmark makes no claims of testing those omitted adjustments.

The `allWalkForward` section shows paired historical MAE/RMSE over all
eligible predictions. `lastQuarterHoldout` shows those same paired metrics
over the last quarter of the *distinct eligible calendar dates*, chosen
chronologically; model constants are **not** tuned to this segment.
The dashboard lists per-market results from that segment. Comparison uses
the same sample for both models and excludes same-day outcomes from training.

The holdout is only flagged as sufficiently populated once it has at least
200 paired projections from at least 20 distinct dates; this is a **review
threshold**, not statistical proof, and comparisons among markets need their
own sample review. Do not equate better stat MAE with higher prop profitability.
No automatic model promotion or calibration occurs; further prospective
validation with independently frozen sportsbook prices is required.

Unit tests validate identical historical inputs, combo support and
same-day chronological isolation. GitHub Actions PR CI runs offline tests.

## Upgrade 19: opponent-defense and rotation shadow study

The offline daily export now includes `contextResearch`, a strictly historical
paired four-way study: NBA EDGE's stat-mean baseline; the Claude-inspired
minutes-and-rate projection; an opponent-position defensive residual adjustment;
and a combination of minutes-rate and defense. All four are scored on the
**same context-qualified completed player-games** using MAE.

**Coverage and leakage rules:** Defense is keyed by the opponent's full ESPN
team name, the player's recorded ESPN position (PG, SG, SF, PF, C), and market.
A defensive ratio from earlier observed-versus-individual-baseline production
is shrunk toward 1.0 with a fixed strength of 60 game-equivalents and capped
at 0.85–1.15. At least 15 prior qualified matchup observations are required.
Same-date games only contribute AFTER every game on that date is predicted.
No lineup, injury, or position is imputed from player names or the current
opponent. Older history without explicit team, position and scoreboard-consistent
opponent is excluded; the report shows coverage skips.

The ESPN boxscore ingest now saves the team's display name, team ID and ESPN
listed player position, and derives the opponent *only if* the scoreboard's
home/away matchup confirms the saved team name. Previously collected
boxscores without team context are not silently retroactively rewritten.
Team/position availability will improve with new ESPN data as it is collected.

The last-quarter window reports a chronological slice of qualified dates;
a minimum of 200 samples spanning 20 dates is needed to flag a review-ready
window. That does not demonstrate statistically significant improvement or
profitable bets. Existing grades, production model, cached sportsbook odds,
5:13 PM Central schedule, ntfy notification, and Odds API credit safeguards
are unchanged. This research makes zero additional paid API requests.

## Upgrade 20: resumable historical ESPN opponent and position backfill

The research comparison previously reported zero opponent-defense evaluations
because older ESPN player-game logs lack verified team/opponent/position context.
`scripts/context_backfill.py` retrieves **existing completed game IDs only**
from ESPN's free game-summary/boxscore endpoint and augments **only** contextual
fields on rows with exactly matching ESPN game and player IDs. Original points,
rebounds, assists, minutes, settled-pick outcomes, and recorded odds are never
overwritten.

Team/opponent labels are cross-checked against the saved scoreboard matchup;
known aliases such as `LA Clippers` vs `Los Angeles Clippers` are normalized.
If a saved matchup contradicts the freshly retrieved ESPN summary, context is
**not** updated. Player positions require explicit PG/SG/SF/PF/C data from the
ESPN athlete entry; missing context is still reported as missing.

### Running the backfill

Use GitHub **Actions → ESPN history context backfill (no odds) → Run workflow**.
Default batch: 48 completed games. A configurable manual batch supports 1–120.
The workflow also runs in bounded off-peak UTC batches at `08:27 UTC` daily
until the game backlog has been inspected. It uses a maximum of 3 concurrent
requests to ESPN's public game-summary endpoint, **never The Odds API**.
The existing `Refresh NBA EDGE picks` workflow keeps its 5:13 PM Central
schedule; both share a concurrency lock to avoid committing snapshots at the
same moment.

Successfully fetched game IDs are stored as
`docs/game_logs.json.contextBackfill.attemptedGameIds`, so games without
a position are not fetched repeatedly. Failed games are retried at most
three times and then flagged for manual review rather than blocking the
rest of the backlog. The source file contains a progress count and most
recent batch summary; `docs/daily_analysis.json.contextBackfill` and
the dashboard display progress. A normal odds/picks refresh preserves the
backfill state rather than resetting it. Runs with no remaining work do
not rewrite the state just to change a timestamp.

Each batch runs the existing **four-way historical model comparison** again,
using only then-available verified context and strictly earlier dates for
opponent-specific signals. Initial batches may still show insufficient
coverage and null MAE values. No adjustment is automatically applied to
production probabilities or betting picks, and this feature makes **zero
additional paid odds requests**.

This uses undocumented public ESPN summary fields; if they change, the
context backfill will leave rows unchanged or flag errors rather than
inventing missing positions/opponents.
