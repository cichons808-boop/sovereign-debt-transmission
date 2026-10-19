# Data definitions

`country` is the two-letter country code, `period` the calendar quarter and `time_index` its contiguous quarterly ordinal. Leads and lags are formed on the complete calendar, before restricting the estimation observations. The local-projection response is `outcome[t+h] - outcome[t-1]`.

## Debt stocks and repayment dates

| Field | Unit and meaning |
|---|---|
| `debt` | Public debt, percentage points of annual GDP |
| `foreign` | Holdings of non-residents, in the same units |
| `cb` | Central-bank holdings |
| `domestic_noncb` | Resident holdings outside the central bank; `debt = foreign + cb + domestic_noncb` |
| `foreign_official_gdp`, `domestic_bank_gdp`, `domestic_nonbank_gdp` | Further creditor partitions, percentage points of GDP |
| `refinance_share` | Principal due within one year divided by the same portfolio's outstanding principal |
| `rollover_centered` | `(refinance_share - common reference median) / 0.10` |

`ownership_frequency` and `ownership_measurement_period` record the frequency and reference date of the ownership observation. Quarterly stocks are dated before the shock; annual stocks use the previous year. `source` and `quarterly_source` identify the creditor tables. `source_group` and `roll_group` identify the country–ownership-source–maturity-source regime used in estimation.

Repayment data have their own fields: `maturity_source`, `maturity_date` and `maturity_frequency` give the source and actual observation date; `maturity_sector`, `maturity_portfolio` and `maturity_valuation` describe the numerator and denominator. These labels matter when comparing a marketable-securities portfolio with the broader general-government stock.

## Monetary shocks and macroeconomic series

| Field | Unit and timing |
|---|---|
| `MP_median`, `CBI_median` | Monetary and central-bank-information surprises; a unit is ten basis points |
| `log_gdp`, `log_prices`, `log_reer` | 100 times the log level; quarterly CPI and REER averages require three observed months |
| `debt_ratio_observed` | Observed quarterly general-government debt/GDP, percentage points |
| `growth_l1`…`growth_l4`, `inflation_l1`…`inflation_l4` | One to four lags of quarterly growth and inflation, in 100-log differences |
| `growth_state`, `inflation_state` | Predetermined four-quarter changes in GDP and prices |
| `debt_accumulation` | `(debt_ratio_observed[t-1] - debt_ratio_observed[t-5]) / 10` |
| `current_account` | Current-account balance, percentage points of GDP, at source frequency |
| `ca_state` | Predetermined current-account/GDP ratio divided by five |
| `reer_state` | `(log_reer[t-1] - log_reer[t-5]) / 10`; positive means preceding appreciation |
| `wti_state`, `spy_state` | Previous-quarter WTI and adjusted SPY 100-log changes, divided by ten |
| `Fed_MP`, `Fed_CBI`, `ECB_MP`, `ECB_CBI` | Global monetary and information controls; an issuer's own authority is excluded |

`ca_state_source` and `ca_state_frequency` distinguish OECD seasonally adjusted quarters, Eurostat unadjusted quarters and previous-year WDI annual observations. Macro outcomes themselves remain quarterly. `policy_group` is the monetary setting and `policy_issuer` the authority supplying the shock; euro-area countries share the ECB. The LP constructor uses `ea_member` as its eligibility flag. In the own-policy files, this flag denotes own-policy eligibility.

The currency extension uses `fx_share`, the previous annual foreign-currency debt fraction, together with `fx_source` and `portfolio`. These retain the source and debt definition used in the comparison. The currency slope is scaled as `fx_share / 0.1`. For the external-deficit slope the code uses `-ca_state`: the balance has already been divided by five, so a unit means a five-point-of-GDP larger deficit. Currency denomination and creditor residence are separate characteristics of the debt.

## Institutional series

`fiscal_retail_ecb_monthly.csv.gz` contains the country, month, measure and original ECB series identifier. BSI household/NPISH deposit stocks are in EUR million; MIR rates on new term deposits and overnight deposits are annual percentages. The Belgian comparison uses July 2023, before subscription, as its baseline and September as the settlement month. The Portuguese baseline is May 2023, before the June certificate redesign.

`fiscal_poland_repricing_monthly.csv.gz` records ROR and DOR principal in PLN million and the NBP reference rate. Annualized policy-rate coupon exposure and annual sensitivity to a 100-basis-point change are in PLN billion. The calculation holds principal fixed while the coupon adjusts; the bonds also retain their contractual maturity dates. The source does not classify purchasers by residence.

The allocation-bound data use Eurostat general-government sector S13, resident creditor ownership and original and remaining maturity. Amounts and widths are in percentage points of GDP. Original-maturity information restricts the feasible amount of short-residual-maturity debt held by residents. These bounds describe the unobserved joint holding, rather than an identified set for the panel-response coefficient.
