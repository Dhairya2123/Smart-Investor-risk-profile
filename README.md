# Smart Investor Risk Profile

An educational tool built from the **53-question Complete Investor Questionnaire**. It profiles an investor on risk tolerance,
risk capacity and risk required, explains the result, checks whether the goal is feasible, shows downside scenarios and their
effect on the goal, and lists **fund categories to research** for each risk profile.
**Not investment advice. It never issues buy/sell instructions.**

## Quick start

```bash
pip install -r requirements.txt
pytest                 # 130+ tests
streamlit run app.py   # opens the dashboard (run THIS file; do not use python app.py)
```

In the app, open the Questionnaire tab, either answer the questions or pick a fictional example investor, and press **Calculate my profile**.

## Tabs

| Tab | What it shows |
|---|---|
| 1 Questionnaire | All 53 questions in 7 sections, with progress and validation |
| 2 Assessment | Section 8 table (tolerance, capacity, required, overall profile, goal feasibility, mismatch), the conflict rule, warnings |
| 3 Goal & allocation | Inflation-adjusted goal feasibility, alternatives if short, illustrative allocation, editable assumptions |
| 4 Crash scenarios | Hypothetical falls, comparison with your stated tolerable decline, estimated impact on the goal |
| 5 Fund categories | Which fund categories (and example schemes to research) fit the profile, with portfolio weights |
| 6 Fund comparison | CAGR, volatility, Sharpe, drawdown, beta, rolling returns on sample, live (mfapi.in) or uploaded NAVs |
| 7 Report & export | Markdown report and Power BI CSV bundle; optional "Save this run" |
| 8 History | Saved runs (scores only) |

## Structure

| File | Purpose |
|---|---|
| `smart_investor/questionnaire.py` | The 53 questions as data, options, scores, weights, validation |
| `smart_investor/risk_engine.py` | Scoring, caps, conflict rule, profile, warnings, explanations |
| `smart_investor/goal.py` | Goal feasibility and alternatives (needed contribution, years, achievable target) |
| `smart_investor/allocation.py`, `crash.py` | Allocation bands, projections, crash simulator, goal impact |
| `smart_investor/funds_catalog.py` | Profile to SEBI fund-category mapping and example schemes |
| `smart_investor/fund_analytics.py`, `data_loader.py` | Fund metrics and NAV loading |
| `smart_investor/report.py`, `export.py`, `persistence.py` | Report, Power BI bundle, optional SQLite history |
| `smart_investor/samples.py` | Fictional example investors (also used by tests) |
| `docs/METHODOLOGY.md` | Why every rule, weight and threshold exists, and the limitations |
| `docs/QUESTION_SCORING.md` | Every question's options, scores and weights (generated from the code) |
| `docs/FUND_MAPPING.md` | Which fund categories fit which profile (generated from the code) |
| `scripts/generate_docs.py` | Regenerates the two generated docs after you change scores or mappings |
| `schema.sql` | PostgreSQL version of the history tables |

## How scoring works (short version)

- **Tolerance** (Section 3 + small experience weight) and **capacity** (financial questions + time horizon, with hard caps for no emergency fund,
  heavy debt, severe loss impact, forced withdrawals and short horizons) are scored 0-100.
- **Required risk** is *calculated* from the goal (target, inflation, current investment, monthly amount, horizon), never guessed.
- **Overall profile = the lower of the capacity-based and tolerance-based profile.** Scores are not averaged, high tolerance cannot override low capacity,
  and the required risk never raises the profile; it only raises a mismatch warning and suggests alternatives.
- Age, occupation, income band, housing and spending style are context only and are not scored.

Change any weight or threshold in `questionnaire.py` / `risk_engine.py`, then run `pytest` and `python scripts/generate_docs.py`.

## Fund categories by profile

| Profile | Equity range | Main categories to research |
|---|---|---|
| Conservative | 10-25% | Short duration, Banking & PSU, Corporate bond, Liquid, small Nifty 50 index fund |
| Moderately Conservative | 25-45% | Nifty 50 index, Flexi cap, Short duration, Corporate bond, Gilt, Liquid |
| Moderate | 45-60% | Nifty 50 index, Flexi cap, Large & mid cap, a little Mid cap, Short duration, Corporate bond, Gilt |
| Moderately Aggressive | 60-80% | Nifty 50 index, Flexi cap, Large & mid cap, Mid cap, Corporate bond, Short duration |
| Aggressive | 80-95% | Nifty 50 index, Flexi cap, Mid cap, Small cap, plus Corporate bond / Short duration |

Details, example schemes and a shortlisting checklist are in `docs/FUND_MAPPING.md`. These are **categories and examples to research, not recommendations**;
names may be outdated, so verify on the AMC factsheet, AMFI or the app's live comparison tab.

## Limitations (read before any real-world use)

- Weights, thresholds and allocation bands are design choices, not regulatory standards; they need validation, user testing and regulatory review.
- Sample fund data is **synthetic**. Never present it as real performance.
- mfapi.in is community-run with no uptime guarantee; verify important figures against AMFI or the AMC.
- Past performance does not guarantee future results; no single metric is a fund recommendation.
- Only the main goal is modelled. The app stores nothing unless you press "Save this run" (scores only, no personal details).

## Power BI

On the Report & export tab, download `powerbi_data.zip`: CSVs in long format (assessment, warnings, allocation, crash scenarios, goal impact, fund shortlist,
fund metrics, NAV history, rolling returns) plus `README.txt` with import steps and suggested visuals.


## Dry-period, sector and scorecard tabs
* **7 Sectors & dry periods**: underwater episodes, dry spells, calendar-year heatmap, rotation ranks, correlation, trend context, and notes against your horizon and tolerable decline.
* **8 Fund scorecard**: within-category percentile ranking from NAV metrics plus factsheet inputs you enter.
* Report and Power BI export include both when loaded. See `docs/DRY_PERIODS.md`. Sample data here is synthetic.
