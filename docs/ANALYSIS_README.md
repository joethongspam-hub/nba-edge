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

## Upgrade 21: prospective EV-only vs risk-adjusted Top 10 research

A **paper-only**, predeclared ranking comparison tests the hypothesis that
our historical Evidence Score might identify exaggerated estimated EV.
Both methods receive the exact same qualifying props from
`scripts/update.py.rank(..., return_candidates=True)`, after existing
minimum historical sample, >4.5% estimated EV, and >3.5 percentage-point
estimated edge screens. Both keep the best one prop per player per game
date and select at most 10.

The original live method ranks purely by descending **estimated EV**.
The challenger ranks by **estimated EV × (Evidence Score / 100)²**.
That formula is deliberately fixed in advance; it is not claimed to be a
calibrated probability, corrected EV, or profitable strategy. Ties use
EV, player, market, and book for deterministic ordering.

Both paper portfolios are frozen together in
`docs/ranking_experiment.json`, at their **original pregame sportsbook
prices**; started games cannot be added, old slates cannot be reconstructed,
and later odds refreshes never replace a saved slate. This is a new
prospective study: no legacy 2026 picks are relabeled as if they were
risk-ranked. Picks overlapping both portfolios share a *single archived
pick and settlement*, and dashboard overlap counts make their dependence
visible. Eligible selections remain paper-only: no bets are placed.

The existing validated ESPN matcher settles each paper selection only on
a **unique matching player, matchup, and game-start window**. Without
that match, a row stays pending; draws at integer lines are pushes.
Recorded 1-unit paper ROI, win rate, and result counts are compared on
`daily_analysis.json.rankingExperiment` and in a new dashboard panel.
At least **100 settled non-push bets in each group** are required even
to flag the study for review; such a sample alone does not demonstrate
statistical superiority because both rankings share selections and
sportsbook probabilities are uncalibrated.

The experiment makes **no additional Odds API queries**: same cached
FanDuel/DraftKings props, same ranking computation, same normal nightly
workflow. Production Top 10, grades, EV thresholds, 5:13 PM Central
schedule, paid-credit reserve, ntfy behavior, and historical tracker are
unchanged. If the first run is already after all game starts, no new
slate is synthesized: the next pregame refresh can freeze the first
eligible comparison.

## Upgrade 22: projection-gap confidence Top 10 (live ranking)

The public **Top daily picks** now prioritizes stats the model projects
**materially above or below the listed sportsbook line**, supported by
historical sample quality and stability, not estimated EV.

After the existing 40-game recency-weighted historical stat projection,
each player/book/market/side gets:

- Signed directional gap: `projection - line` for an **Over**, or
  `line - projection` for an **Under**. A wrong-direction gap is excluded.
- Volatility-normalized gap: directional gap / historical weighted stat
  deviation. A larger raw points gap must overcome larger points volatility
  before outranking a stable 2-rebound gap.
- **Pure historical evidence**: sample size (35 points), recent minutes (20),
  minutes stability (20), stat consistency (15), minus up to 25 points for
  games older than 90 days. Unlike the earlier grade calculation, it
  **excludes** the bookmaker-implied edge score entirely.
- Ranking strength: `normalizedGap * (evidenceScore / 100)²`. This
  deterministic research ranking score is **not** a hit probability, EV,
  statistical confidence interval, or guaranteed advantage.

To qualify, a pick needs **at least 20** usable historical games, **at most
20** games older than 90 days among its last 40, evidence score **≥60**
(Grade C or B; A remains unavailable), a directional raw discrepancy of
**≥0.5 stat units**, and a normalized gap of **≥0.75 standard deviations**.
The app picks at most ten ranked candidates and keeps only one prop per
player per game date. It displays fewer than ten when fewer qualify.
All eight supported player and combo markets are scanned, with no
favorite/Over/Under restrictions.

The Top 10 table now shows **projected stat / sportsbook line**, signed
projected gap, and evidence score instead of estimated hit percentage,
edge, or estimated EV. FanDuel/DraftKings odds remain as informational
line metadata. This does **not** imply that a large gap is a profitable bet
at any available price. Historical projections do not fully account for
injuries, matchup, lineup changes, or rotations.

**Continuity:** The independent, already-frozen Upgrade 21 paper experiment
keeps its original EV-only and evidence-weighted EV cohorts and original
thresholds, unaffected by the new live ranking. Original historical tracker
outcomes are never rewritten; new tracker rows freeze projection, gap,
normalized gap, evidence, and ranking method. Internal probability/EV
diagnostics remain available for audit; they do not choose today's Top 10.
The schedule, ntfy, cache, free ESPN backfill, quota guard, and paid odds
request count are unchanged. Old cached `docs/data.json` snapshots will
show their original picks until the next full recomputation.

## Upgrade 23: explain every projection-based Top 10 rejection

The normal refresh now attaches `selectionDiagnostics` to
`docs/data.json` and `docs/daily_analysis.json`, and displays a
**Why props did or didn't qualify** panel on the public dashboard.
This information comes from the **exact same** iteration of cached
DraftKings/FanDuel props and player histories used to create the live
Top 10. No extra Odds API or ESPN requests are made.

The diagnostic uses **sequential, mutually exclusive first-failure**
categories: (1) fewer than 15 usable games; (2) only 15–19 usable
games; (3) more than 20 games older than 90 days; (4) pure historical
evidence score under 60; (5) projection on the wrong side of the line;
(6) positive directional gap under 0.5 stat units; (7) directional
gap under 0.75 historical standard deviations; or (8) qualified.
Each prop is counted exactly once and the category totals must
equal the input prop count. A prop excluded early could also fail
later checks; the categories are **not** independent rejection totals.

The report also includes counts **by prop market**, the number of
qualified sportsbook props before one-per-player/date deduplication,
the number of eligible player/date pairs, and the final Top 10 count.
No threshold, Top 10 selection, existing EV paper experiment,
odds budget/reserve, schedule, ntfy notification, or historical
betting result was altered.

If a prior slate only has a legacy snapshot with no original
full-slate prop cache, the app **does not** re-request paid odds solely
to fill in this diagnostic. Such a slate reports
`selectionDiagnostics.status = not_collected` until the next
eligible refresh with available raw cached prop lines. Historical
slates cannot be retroactively diagnosed without their inputs.

## Upgrade 24: evidence-score sensitivity research (no live changes)

The `scripts/evidence_research.py` module runs **offline during the normal
picks refresh**, using the **same saved sportsbook props**, the **same ESPN
player logs**, and the **existing `ranking_probability` implementation**.
It performs no paid/free network requests of its own. Results are saved to
`docs/data.json.evidenceResearch`, copied into
`docs/daily_analysis.json.evidenceResearch`, and shown on the dashboard.

It examines how much of the current historical evidence score comes from
sample size (maximum 35), recent playing minutes (20), minutes consistency
(20), stat consistency (15), and age penalty (up to 25 deducted). The
study reports average component points across props with 20+ games and
no more than 20 old games, and within that pool those meeting the fixed
directional projection gap tests. It also reports evidence-score bands.

A **predeclared what-if table** compares:
- Current production rules: 20 games, evidence >=60, minutes CV tolerance .35
- Evidence cutoffs 55, 50, and 45 (all else unchanged)
- Higher minutes CV tolerance .50 (but still 60 evidence and 20 games)
- 15 minimum games and evidence >=55

All scenarios still enforce <=20 historical games older than 90 days,
correct Over/Under direction, at least a 0.5-unit gap, a normalized
gap >=0.75 of the stat's historical variability, and one prop per player
per game date. The table shows qualified prop rows, unique player/game
dates, hypothetical Top 10 size, and average evidence of those ten.
The **current** scenario is regression-tested to yield the exact same
qualifying count, unique-player count, and Top 10 size as the production
ranker, so the what-if study is not a second incompatible projection model.

**Important limitations:** These are *same-slate selection counts*, NOT
predictions graded against future outcomes. Multiple sportsbook
offerings for the same player/game are correlated; the output does not
claim independent evidence or a realized win rate. Alternatives were
considered after inspecting a zero-pick slate, so they must not be
promoted based solely on generating more picks. The existing production
thresholds, grade calculation, ranking, prior tracker's records,
prospective EV-ranking paper experiment, ntfy, schedule, ESPN history
backfill, cached odds behavior, and minimum Odds API balance reserve are
**unchanged**. Rerunning the standard refresh with a valid same-slate
cache recomputes this study with **zero extra paid odds calls**.

## Upgrade 25: pregame-causal evidence redesign benchmark

The production evidence/grades and projection Top 10 remain **unchanged**.
The alternative evidence model is shadow-only. The redesigned rule is
deliberately simple and predeclared: sample credit
`35*n/(n+4)` rather than linear `35*n/40`, penalty
`15*(oldGames/n)` rather than `1.5*oldGames`, and minutes CV
tolerance `.45` rather than `.35`. The recent minutes and
stat-consistency terms are unchanged. The redesign is not a new hit
probability and does not automatically raise grades.

The same-slate evidence sensitivity study includes a new
**Redesigned-score 60 / 20 games** scenario; all directional-gap
and volatility-normalized-gap checks remain identical. The scenario
reports hypothetical eligible sportsbook rows and one-per-player Top 10
size but does not record picks as bets.

For a **historical projection-error reliability study**, the new
`scripts/evidence_walkforward.py` processes all eight supported
markets, each player, and each game date chronologically. For each
target game, it looks back to **strictly earlier dates**, recomputes
the same 40-game recency-weighted projection and evidence inputs,
and compares its forecast with the actual ESPN boxscore value.
The same prediction/error is attributed to each evidence formula.
Old-game penalties are anchored to the *historical target date*,
not the day the analysis happens. Current-day games never appear
in another same-day game's training history. The final quarter
of distinct observed dates is held out for descriptive reporting,
with at least **20 dates and 200 player-game-market outcomes**
required for a minimum-sample review flag.

The report includes overall and last-quarter paired sample sizes,
score-60 coverage, raw and volatility-normalized MAE within selected
groups, and score-bucket diagnostics. The benchmark may identify
whether higher evidence scores correlate with lower errors, but
**changing evidence scores does not itself improve projected stat
accuracy**. As higher scores select a different collection of
historical games, subgroup MAE comparisons cannot establish causal
superiority. Eight combo/stat markets from one player game are
correlated and must not be interpreted as independent bets.
Retrospective boxscores contain no historical sportsbook closing
lines, so this is **not a bet-selection profit or ROI backtest**.
Changes prompted by a zero-pick slate are exploratory; meaningful
out-of-sample and prospective frozen-prop evidence would be required
before promoting the new evidence system.

`docs/daily_analysis.json.evidenceScoreWalkForward` and a new
dashboard panel expose the analysis. The report uses existing saved
ESPN history only, including data added by the free context backfill.
It makes **zero** additional Odds API calls and zero ESPN network
requests; the daily refresh already had the necessary inputs.
Production grades, Top 10, tracker, previous paper experiment,
quota/caching protections, ntfy, and schedule are unmodified.

## Upgrade 26: prospective paper-only projection-first Top 10

Following the zero-production-pick slate, a separate **projection-first**
research list tests selecting the largest player-stat vs sportsbook-line
discrepancies without the live evidence-score >=60 hard cutoff or any
estimated-EV filter. This is a paper simulation; it does **not** replace
the production Top 10 or modify historical published tracker rows.

Each eligible sportsbook prop uses the existing projection and historical
evidence calculation, then must have at least 15 usable history games,
at most 20 games older than 90 days, a correctly directed Over/Under
projection gap of at least 0.5 stat units, and a volatility-standardized
gap of at least 0.75 historical standard deviations. Rank by
`normalizedGap * (0.5 + evidenceScore/200)`; compare different
markets using standardized gaps, not raw points, and use score quality
as a ranking adjustment (not an exclusion at 60). The paper board shows
`limited` (score <45), `moderate` (45–59) or `strong` (60+)
historical *evidence labels*, not validated bet-hit probabilities or A/B
confidence grades. Maximum one prop per player/game date and ten props
per slate; fewer when no meaningful projection gaps are present.

Prospective selections are frozen before tipoff in
`docs/projection_shadow.json` with the original model inputs, line,
book, price, projected gap, evidence, and time. Later refreshes cannot
reprice, replace or retroactively synthesize an old slate. The same
unique player/matchup/game-time ESPN matching used by the existing
paper EV experiment grades win/loss/push and tracks one-unit paper
performance; a minimum of 100 verified non-push decisions is required
even to consider review. Overlapping selections and combo markets are
correlated, and this ranking is not a profitability guarantee.

The export reads the paper archive into
`docs/daily_analysis.json.projectionShadow`. A separate dashboard
table displays its latest frozen Top 10 and verified paper record. The
regular 5:13 PM CT refresh commits the archive; rerunning with
existing same-day cached odds costs **zero** additional paid credits.
Production Top 10 selection, grades, betting tracker, prior EV study,
data caching, quota protections, ntfy and schedule remain unchanged.
