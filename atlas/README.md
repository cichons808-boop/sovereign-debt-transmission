# Global Monetary Transmission Atlas

Additive research branch of **Creditor Residence, Refinancing, and Monetary Transmission**. Existing `src/`, `data/` and reproducible research are retained. The atlas has its own data, estimates, source audit and notebooks. Research snapshot: 22 November 2026.

Each LP has at most four economic regressors: one shock, one predetermined characteristic, their interaction, and one lag of outcome growth. Fixed effects and seasonality are nuisance dummies. There is no VAR, VARX, LASSO, machine learning or large moderator dictionary in this design.

## What is actually being built

- **Wide domestic/inherited universe:** CWY annual shocks, with country-year source method and anchor identities. The original workbook contains 176 countries, ends in 2019 and is not homogeneous high-frequency identification.
- **Event identification comparisons:** Bolhuis–Das–Yao daily swaps; the published JK ECB vintage; independent reconstructions using current USMPD and EA-EMPD raw observations; official UKMPD target and path factors kept separate.
- **Reaction-function reconstructions:** annual CWY-style three-lag and separate one-lag rules; observed quarterly one-lag rules. These are a weaker identification class and must never be described as exogenous intraday surprises.
- **External monetary spillovers:** separate current Fed and ECB shock experiments on worldwide observed outcomes. A common Fed realization is one monetary issuer, regardless of how many recipient countries are observed. External responses are never labelled domestic policy responses.

Current raw event endpoints: USMPD 28 October 2026; EA-EMPD meetings 11 June 2026 (speeches in the source through 30 June); UKMPD 30 April 2026. The obsolete ECB `/annex/` workbook ends October 2025; the current `/other/` workbook contains the extended dataset and uses different quote construction. Both vintages are retained and their overlap is checked. The author's newest-named BDY file actually ends in 2022, despite a website description of 2000–2024.

New IMF QNEA and CPI observations expand the macro universe beyond the original project: 107 individual economies with observed real quarterly GDP and 189 with headline CPI. Coverage and eligibility after joins differ. Country and territory counts must not be confused with independent monetary authorities.

## Reproduction

From the repository root, use Python 3.12 with the original `requirements.txt` and `atlas/requirements.txt`.

```bash
python -m pip install -r requirements.txt -r atlas/requirements.txt
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m atlas.run baseline
python -m atlas.run chunk --moderator F01
python -m atlas.run report
python -m atlas.run validate
```

The saved processed panels reproduce the regression inputs. Raw re-acquisition / construction modules are explicit:

```bash
python -m atlas.macro_expansion
python -m atlas.run audit
python -m atlas.run fresh
python -m atlas.external
python -m atlas.run reconstruct
```

Public APIs and source websites may revise files or deny direct downloads. The UK workbook was retrieved through the ordinary public download interface after direct HTTP access failed. Source checksums, exact URLs, native frequencies and access failures are recorded. No missing dataset is silently replaced by simulated data. For exact regression replication prefer the preserved panels over a live API refresh.

## Research records

- `audit/dataset_comparison.csv`: downloaded versus usable coverage.
- `audit/cwy_country_year_identification.csv`: construction and policy anchor of every observed annual CWY value.
- `audit/worldwide_country_gap_inventory.csv`: all ISO countries/territories, including unresolved sources; this is not a claim that every national website has already been searched.
- `audit/*reconstruction_validation.json`: numerical methodology checks and source-vintage comparisons.
- `variable_registry.csv`: one row per received/proposed measure. The supplied catalogue ended mid-F10; that truncation is recorded rather than inventing the absent catalogue.
- `results/baseline/`: all country LPs and attempted panel baselines, including time-absorbed common shocks.
- `results/chunks/<ID>/`: one structural characteristic only, coefficients, raw p-values, informational BH q-values, block-wild diagnostics, covariance matrices and observation keys.
- `notebooks/`: short empirical notes, including nulls, unexpected signs and estimation exclusions.
- `checkpoints.jsonl`: stage and chunk completion records. No unfinished work is represented as continuing in the background.

Baseline horizons are 0–5 years or 0–12 quarters. Outcomes are cumulative log-level changes relative to the pre-shock period. Headline CPI is a price-level response, not a change in the inflation rate. Quarterly CPI averages require all three actually observed months. Annual moderators retain annual observation dates and enter as prior-calendar-year exposure states; no annual outcome is interpolated into quarters.

Inference uses calendar-aggregated Bartlett HAC scores, so common currency-union shocks, global dependence and overlapping LP outcomes are retained. Time fixed effects explicitly absorb common shock main effects. Restricted calendar-block wild p-values and BH adjustments supplement the raw HAC p-values. Small samples, generated Taylor innovations, source heterogeneity and multiple exploratory comparisons limit interpretation. A positive interaction or country point estimate is not proof of expansionary monetary policy.

This is an evolving empirical atlas, not a finished paper or a completed test of the entire structural-variable catalogue. See the generated notebook and chunk status files for exactly what ran.
