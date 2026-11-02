# Research directions enabled by the data expansion

These are proposed research designs and data requirements. They are not
claims of newly established causal effects. The exact country/date support
comes from the live coverage reports.

| Question | Relevant source families | Necessary definition or design check |
|---|---|---|
| Does creditor residence change monetary transmission at high refinancing exposure? | Existing IMF/FHL ownership; BIS and QPSD maturity; BDY, EA-MPD, USMPD; macro outcomes | Match the issuer, portfolio and observation date; retain distinct shock constructions |
| Do currency denomination and creditor residence have different effects? | BIS debt securities; Eurostat currency; QEDS; IMF IIPCC and ownership | Avoid treating foreign-currency debt as foreign-held debt; verify joint cells or state bounds |
| How does central-bank portfolio runoff alter fiscal repricing? | IMF MFS central-bank balance sheets, BIS central-bank assets, ownership, government interest costs | Central-bank assets and central-bank government-debt holdings are different series |
| Does global dollar funding amplify fiscal stress in emerging markets? | BIS GLI, LBS/CBS; QEDS/IDS; BOP/IIP; exchange rates and US monetary events | Separate lender residence, bank nationality, borrower location and currency |
| Where is the sovereign–bank feedback strongest? | IMF GFS counterparty flows, MFS bank data and FSI; BIS credit; government yields | Bank holdings of government claims differ from total domestic creditor holdings |
| How fast do floating-rate and inflation-indexed bonds transmit tightening to budgets? | US Treasury security tables; original Polish ROR/DOR evidence; interest expense and CPI | Keep cash-flow timing, indexation lags, redemption flows and outstanding principal distinct |
| Do institutional quality and financial depth alter monetary–fiscal interactions? | WGI, GFDD, WDI, ownership/maturity panels | Use country-year institutions at their actual frequency and pre-specify a limited interaction family |
| How do IMF fiscal forecasts react to policy surprises and debt structure? | WEO/FM archived releases, monetary events, maturity and ownership | Use archived vintages and release dates; exclude hindsight from current revised data |
| Is long-run fiscal adjustment different after financial deepening? | IMF HPD/GDD; historical WDI; financial development and credit | Audit historical borders, missing spells and changes in government coverage |
| Does decentralization change fiscal propagation? | IMF FD; GFS/COFOG; public-sector debt definitions | Distinguish subnational debt from consolidated general-government debt |
| How do yield-curve and deposit-rate channels interact with retail debt? | ECB YC/MIR/BSI; monetary events; original institutional episodes | Use contract-specific retail data and matched deposit instruments; do not classify all households as residents without evidence |
| Can global forecasting models improve macro-financial forecasts across countries? | WDI/GEM, CPI, rates, yield curves, credit, fiscal/external stocks | Rolling-origin evaluation; country/time splits; release lags; comparisons with strong conventional forecasts |
| Do climate/energy exposures change fiscal sensitivity to global tightening? | WB ESG, trade/energy indicators, external debt and policy events | Confirm exposure definitions and publication timing before adding interactions |

## Concrete data products

- Native annual WDI panel, with one variable dictionary and row-level lineage.
- Original event-window panels for USMPD and EA-MPD; distinct BDY release panels.
- Observed quarterly refinancing shares from compatible BIS security cells.
- Original frequency ownership and currency data bridged from the frozen project.
- Provider/dataset/country/frequency coverage tables and a series dictionary.
- Download manifests, original SHA256 and normalized partition checksums.

## Priority for extensions

First establish the post-2022 shock coverage available for each issuer and the
overlap with native ownership/maturity observations. Then resolve fiscal
sector and unit compatibility. After that, construct a fixed analysis sample
and its release calendar. Large bilateral banking/portfolio positions and
genuine archived releases add useful dimensions as storage grows.

Downloaded event windows or newer filenames alone do not establish an extended
identification sample. A release can revise values without adding dates; the
coverage report and source dictionary are the deciding evidence.

## Sources verified on 2026-11-02, acquisition still pending

- The [World Bank creditor API guide](https://worldbank.github.io/debt-data/creditor-composition/creditor-data-python.html)
  confirms four IDS dimensions, including `counterpart-area`. Ordinary indicator
  queries default to world creditors. A dedicated adapter can support bilateral
  creditor concentration and common-lender exposure; preserve the external PPG
  portfolio and lender codes rather than equating them with debt currency.
- The [IDS archive table](https://www.worldbank.org/en/programs/debt-statistics/idr/products)
  links the 2022–2025 releases recorded in the extension catalog. They can support
  debt-revision sensitivity tests after workbook contents and availability are
  verified. The catalog often provides only a month; that is not an exact release
  date. A generic filename alone does not prove an immutable historical vintage.
- The [DG ECFIN fiscal governance database](https://economy-finance.ec.europa.eu/economic-research-and-databases/economic-databases/fiscal-governance-database_en)
  supplies rule, medium-term framework and fiscal-institution indices plus survey
  answers. These could describe heterogeneity in fiscal responses. Legal scope,
  methodology changes and actual overlap must be checked before estimation.
- The downloaded IMF catalog identifies `IMF.FAD/WORLD/3.0.1`,
  `IMF.STA/IRFCL/12.0.0` and `IMF.STA/IL/13.0.1`. WoRLD can add revenue composition;
  reserves/liquidity can distinguish gross debt exposure from liquidity buffers.
  Fetch each DSD before choosing keys. The ECB catalog identifies `ECB/SHS/1.0`
  for securities holdings; actual publicly available holder/issuer cells need
  inspection before asserting joint coverage.
- [IMF fiscal rules/councils](https://www.imf.org/external/datamapper/datasets/FR_FC)
  offers another institutional extension. Direct file URLs, workbook definitions
  and the exact country count remain unresolved; this is not integrated data.

These are research opportunities and pending acquisitions, not new causal
findings or an increase in measured country coverage.
