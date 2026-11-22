# Chunk F04: Domestic private sovereign holdings excluding central bank / GDP

Status: core country/panel/external specifications executed; Model E diagnostics executed where supported. This is exploratory research, not a causal finding about changing the characteristic itself.

Mechanism: Resident creditor interest income versus bank-sovereign exposure and fiscal adjustment.

Theoretical direction: ambiguous. No expected sign is treated as an empirical result.

Source / verified series: Fang-Hardy-Lewis full 101-country file; official IMF/Eurostat extension / `fhl_holdings.domestic_private_gdp; official_expanded_ownership_annual.domestic_noncb`.

Dating: only the prior calendar year's genuinely observed characteristic is used. Its native frequency remains annual in quarterly LPs. It is a predetermined exposure state, never an interpolated quarterly observation. Missing prior years are not filled.

Scaling: one unit of Z is 10.0 percent_of_GDP; centering is fixed at 20.0. The interaction is a change in the shock response per one unit of Z. A positive gamma does not by itself imply that the total GDP response is positive.

Identification concern: domestic outside-central-bank is a provider sector definition; nonbank public entities may be included.

Observed characteristic coverage: 102 economies, 1989–2025, 1855 country-year values. Effective LP support is in `coverage.csv` and differs by outcome and horizon.

Attempted specifications: 11190; estimated: 5102; failures: 0. Rank/variation/sample exclusions remain in the attempt log.

## Global interactions at prespecified horizons

| universe                  | outcome   |   horizon |   estimate |        se |     p_raw |   q_BH_informational |    n |   n_countries |   n_issuers |
|:--------------------------|:----------|----------:|-----------:|----------:|----------:|---------------------:|-----:|--------------:|------------:|
| H_BDY_daily               | gdp       |         0 | -0.011593  | 0.011091  | 0.29873   |             0.765    | 1439 |            20 |          16 |
| H_BDY_daily               | gdp       |         4 |  0.010992  | 0.034137  | 0.74822   |             0.88425  | 1439 |            20 |          16 |
| H_BDY_daily               | gdp       |         8 |  0.041142  | 0.035413  | 0.24843   |             0.765    | 1439 |            20 |          16 |
| H_BDY_daily               | gdp       |        12 |  0.040223  | 0.033107  | 0.22761   |             0.765    | 1427 |            20 |          16 |
| H_BDY_daily               | cpi       |         0 |  0.0057504 | 0.0061975 | 0.35598   |             0.88431  | 1311 |            18 |          14 |
| H_BDY_daily               | cpi       |         4 |  0.017893  | 0.025372  | 0.48252   |             0.88431  | 1311 |            18 |          14 |
| H_BDY_daily               | cpi       |         8 |  0.019241  | 0.046104  | 0.67744   |             0.88431  | 1311 |            18 |          14 |
| H_BDY_daily               | cpi       |        12 |  0.016684  | 0.051824  | 0.74826   |             0.88431  | 1311 |            18 |          14 |
| H_ECB_reconstructed_2026  | gdp       |         0 | -0.014461  | 0.068964  | 0.83433   |             0.90386  |  669 |            19 |           1 |
| H_ECB_reconstructed_2026  | gdp       |         4 | -0.018563  | 0.1889    | 0.92192   |             0.92192  |  568 |            14 |           1 |
| H_ECB_reconstructed_2026  | gdp       |         8 |  0.16438   | 0.12876   | 0.20487   |             0.66582  |  497 |            11 |           1 |
| H_ECB_reconstructed_2026  | gdp       |        12 |  0.30337   | 0.13096   | 0.022806  |             0.27951  |  424 |             5 |           1 |
| H_ECB_reconstructed_2026  | cpi       |         0 | -0.047224  | 0.028974  | 0.10607   |             0.12535  |  778 |            20 |           1 |
| H_ECB_reconstructed_2026  | cpi       |         4 | -0.1278    | 0.071412  | 0.076417  |             0.11038  |  716 |            20 |           1 |
| H_ECB_reconstructed_2026  | cpi       |         8 | -0.13208   | 0.052494  | 0.013458  |             0.034992 |  597 |            14 |           1 |
| H_ECB_reconstructed_2026  | cpi       |        12 | -0.024134  | 0.066678  | 0.71819   |             0.71819  |  520 |            11 |           1 |
| T_reconstructed_annual_1L | gdp       |         0 |  0.038601  | 0.024556  | 0.12495   |             0.74973  |  848 |            40 |          40 |
| T_reconstructed_annual_1L | gdp       |         2 |  0.074799  | 0.10072   | 0.46293   |             0.79145  |  811 |            40 |          40 |
| T_reconstructed_annual_1L | gdp       |         5 |  0.0050157 | 0.11025   | 0.96401   |             0.96401  |  754 |            40 |          40 |
| T_reconstructed_annual_1L | cpi       |         0 | -0.16948   | 0.0829    | 0.048499  |             0.096999 |  847 |            40 |          40 |
| T_reconstructed_annual_1L | cpi       |         2 | -0.30733   | 0.14222   | 0.038052  |             0.096999 |  810 |            40 |          40 |
| T_reconstructed_annual_1L | cpi       |         5 | -0.088989  | 0.25748   | 0.73205   |             0.73205  |  753 |            40 |          40 |
| T_reconstructed_quarterly | gdp       |         0 | -0.0039367 | 0.01505   | 0.79402   |             0.9442   | 2480 |            33 |          33 |
| T_reconstructed_quarterly | gdp       |         4 |  0.020328  | 0.024731  | 0.4125    |             0.9442   | 2435 |            33 |          33 |
| T_reconstructed_quarterly | gdp       |         8 | -0.02785   | 0.033276  | 0.40408   |             0.9442   | 2363 |            33 |          33 |
| T_reconstructed_quarterly | gdp       |        12 | -0.0096338 | 0.038815  | 0.80436   |             0.9442   | 2291 |            33 |          33 |
| T_reconstructed_quarterly | cpi       |         0 | -0.020097  | 0.010746  | 0.063493  |             0.43916  | 2483 |            33 |          33 |
| T_reconstructed_quarterly | cpi       |         4 | -0.047237  | 0.045569  | 0.30169   |             0.43916  | 2464 |            33 |          33 |
| T_reconstructed_quarterly | cpi       |         8 | -0.051959  | 0.063093  | 0.41162   |             0.43916  | 2398 |            33 |          33 |
| T_reconstructed_quarterly | cpi       |        12 | -0.05071   | 0.064371  | 0.43222   |             0.43916  | 2326 |            33 |          33 |
| W_CWY_annual              | gdp       |         0 | -0.030164  | 0.041485  | 0.47299   |             0.47299  | 1476 |            72 |          51 |
| W_CWY_annual              | gdp       |         2 | -0.14449   | 0.07544   | 0.065362  |             0.13072  | 1476 |            72 |          51 |
| W_CWY_annual              | gdp       |         5 | -0.24715   | 0.10728   | 0.02859   |             0.085771 | 1476 |            72 |          51 |
| W_CWY_annual              | cpi       |         0 |  0.034861  | 0.065961  | 0.60117   |             0.72141  | 1416 |            71 |          51 |
| W_CWY_annual              | cpi       |         2 |  0.11542   | 0.10909   | 0.29875   |             0.51723  | 1416 |            71 |          51 |
| W_CWY_annual              | cpi       |         5 |  0.22236   | 0.20583   | 0.2889    |             0.51723  | 1416 |            71 |          51 |
| W_external_USA_annual     | gdp       |         0 | -0.035556  | 0.035769  | 0.32936   |             0.32936  | 1556 |            75 |           1 |
| W_external_USA_annual     | gdp       |         2 | -0.16273   | 0.059764  | 0.011867  |             0.023735 | 1508 |            75 |           1 |
| W_external_USA_annual     | gdp       |         5 | -0.19471   | 0.063523  | 0.0058748 |             0.017624 | 1436 |            75 |           1 |
| W_external_USA_annual     | cpi       |         0 | -0.079175  | 0.044624  | 0.087735  |             0.52462  | 1494 |            73 |           1 |
| W_external_USA_annual     | cpi       |         2 | -0.07697   | 0.12284   | 0.53685   |             0.9352   | 1446 |            73 |           1 |
| W_external_USA_annual     | cpi       |         5 |  0.081772  | 0.25254   | 0.74929   |             0.9352   | 1374 |            73 |           1 |
| W_external_USA_quarterly  | gdp       |         0 | -0.066253  | 0.087065  | 0.4483    |             0.50672  | 4062 |            74 |           1 |
| W_external_USA_quarterly  | gdp       |         4 | -0.19682   | 0.19704   | 0.32007   |             0.44456  | 3905 |            69 |           1 |
| W_external_USA_quarterly  | gdp       |         8 | -0.4129    | 0.31667   | 0.19513   |             0.38226  | 3744 |            65 |           1 |
| W_external_USA_quarterly  | gdp       |        12 | -0.61037   | 0.45916   | 0.18674   |             0.38226  | 3586 |            58 |           1 |
| W_external_USA_quarterly  | cpi       |         0 |  0.033705  | 0.017096  | 0.051081  |             0.11677  | 6271 |            91 |           1 |
| W_external_USA_quarterly  | cpi       |         4 |  0.074443  | 0.04219   | 0.080429  |             0.11677  | 6159 |            91 |           1 |
| W_external_USA_quarterly  | cpi       |         8 |  0.21665   | 0.12619   | 0.08893   |             0.11677  | 5969 |            86 |           1 |
| W_external_USA_quarterly  | cpi       |        12 |  0.34224   | 0.19845   | 0.087641  |             0.11677  | 5812 |            83 |           1 |

Raw p-values are the main reported test statistics. BH q-values and restricted block-wild p-values are informational. Calendar score HAC preserves common monetary issuers and overlapping outcome windows. Few effective time blocks limit inference, especially at long horizons.

## Interpretation limits

The CWY world sample mixes identification methods and inherited shocks. Taylor innovations are a separate weaker identification class. External Fed/ECB models measure spillovers. Intraday US/ECB reconstructions retain their own units and vintages. None are spliced into a single artificial shock series.

No coefficient ranking or raw p-value identifies an expansionary monetary response on its own. The total conditional response and its uncertainty must be inspected; time effects absorb common shock main effects in external/currency-union panels.

## Recorded exclusions / failures

insufficient_observations       5995
insufficient_supported_panel      93
