# Chunk R01: Sovereign principal refinancing within one year

Status: core country/panel/external specifications executed; Model E diagnostics executed where supported. This is exploratory research, not a causal finding about changing the characteristic itself.

Mechanism: Faster repricing of sovereign interest payments and creditor income.

Theoretical direction: ambiguous. No expected sign is treated as an empirical result.

Source / verified series: Observed debt schedules in existing official-expansion inventory / `official_expanded_maturity_candidates.refinance_share`.

Dating: only the prior calendar year's genuinely observed characteristic is used. Its native frequency remains annual in quarterly LPs. It is a predetermined exposure state, never an interpolated quarterly observation. Missing prior years are not filled.

Scaling: one unit of Z is 0.1 share_of_source_government_portfolio; centering is fixed at 0.2. The interaction is a change in the shock response per one unit of Z. A positive gamma does not by itself imply that the total GDP response is positive.

Identification concern: remaining maturity, not original maturity; government portfolios and valuations differ by source.

Observed characteristic coverage: 46 economies, 1995–2025, 864 country-year values. Effective LP support is in `coverage.csv` and differs by outcome and horizon.

Attempted specifications: 7846; estimated: 4432; failures: 0. Rank/variation/sample exclusions remain in the attempt log.

## Global interactions at prespecified horizons

| universe                  | outcome   |   horizon |   estimate |       se |     p_raw |   q_BH_informational |    n |   n_countries |   n_issuers |
|:--------------------------|:----------|----------:|-----------:|---------:|----------:|---------------------:|-----:|--------------:|------------:|
| H_BDY_daily               | gdp       |         0 |  0.0050356 | 0.046958 | 0.91484   |             0.91484  | 2132 |            31 |          18 |
| H_BDY_daily               | gdp       |         4 | -0.059797  | 0.062881 | 0.34421   |             0.84843  | 2132 |            31 |          18 |
| H_BDY_daily               | gdp       |         8 |  0.048868  | 0.074397 | 0.51297   |             0.84843  | 2132 |            31 |          18 |
| H_BDY_daily               | gdp       |        12 |  0.090167  | 0.070565 | 0.20465   |             0.84843  | 2119 |            31 |          18 |
| H_BDY_daily               | cpi       |         0 |  0.0028607 | 0.018178 | 0.87531   |             0.87531  | 1971 |            29 |          16 |
| H_BDY_daily               | cpi       |         4 | -0.070856  | 0.081963 | 0.38964   |             0.59869  | 1971 |            29 |          16 |
| H_BDY_daily               | cpi       |         8 | -0.10588   | 0.1126   | 0.3496    |             0.59869  | 1971 |            29 |          16 |
| H_BDY_daily               | cpi       |        12 | -0.1399    | 0.12694  | 0.27339   |             0.59869  | 1971 |            29 |          16 |
| H_ECB_reconstructed_2026  | gdp       |         0 |  0.32013   | 0.12838  | 0.014256  |             0.18533  | 1156 |            19 |           1 |
| H_ECB_reconstructed_2026  | gdp       |         4 |  0.42453   | 0.34054  | 0.2155    |             0.60497  | 1101 |            15 |           1 |
| H_ECB_reconstructed_2026  | gdp       |         8 |  0.41865   | 0.54481  | 0.44416   |             0.60497  | 1081 |            15 |           1 |
| H_ECB_reconstructed_2026  | gdp       |        12 |  0.5162    | 0.60589  | 0.39649   |             0.60497  | 1057 |            14 |           1 |
| H_ECB_reconstructed_2026  | cpi       |         0 |  0.055839  | 0.044041 | 0.20758   |             0.20758  | 1208 |            20 |           1 |
| H_ECB_reconstructed_2026  | cpi       |         4 |  0.33094   | 0.13566  | 0.016398  |             0.050862 | 1182 |            20 |           1 |
| H_ECB_reconstructed_2026  | cpi       |         8 |  0.44498   | 0.20093  | 0.029061  |             0.050862 | 1113 |            15 |           1 |
| H_ECB_reconstructed_2026  | cpi       |        12 |  0.48806   | 0.19804  | 0.0155    |             0.050862 | 1093 |            15 |           1 |
| T_reconstructed_annual_1L | gdp       |         0 | -0.14827   | 0.089716 | 0.10919   |             0.16378  |  423 |            19 |          19 |
| T_reconstructed_annual_1L | gdp       |         2 | -0.025911  | 0.087831 | 0.77025   |             0.77025  |  405 |            19 |          19 |
| T_reconstructed_annual_1L | gdp       |         5 | -0.45373   | 0.25891  | 0.092467  |             0.16378  |  369 |            19 |          19 |
| T_reconstructed_annual_1L | cpi       |         0 | -0.18767   | 0.066313 | 0.0083623 |             0.050174 |  423 |            19 |          19 |
| T_reconstructed_annual_1L | cpi       |         2 | -0.2292    | 0.17981  | 0.21329   |             0.31994  |  405 |            19 |          19 |
| T_reconstructed_annual_1L | cpi       |         5 | -0.044889  | 0.28935  | 0.87801   |             0.90241  |  368 |            19 |          19 |
| T_reconstructed_quarterly | gdp       |         0 | -0.06914   | 0.039369 | 0.081586  |             0.15141  | 1591 |            23 |          23 |
| T_reconstructed_quarterly | gdp       |         4 | -0.22507   | 0.13193  | 0.090665  |             0.15141  | 1531 |            22 |          22 |
| T_reconstructed_quarterly | gdp       |         8 | -0.34748   | 0.20522  | 0.093174  |             0.15141  | 1479 |            22 |          22 |
| T_reconstructed_quarterly | gdp       |        12 | -0.43562   | 0.22648  | 0.057034  |             0.15141  | 1415 |            19 |          19 |
| T_reconstructed_quarterly | cpi       |         0 | -0.024801  | 0.034812 | 0.47756   |             0.95314  | 1603 |            23 |          23 |
| T_reconstructed_quarterly | cpi       |         4 | -0.11878   | 0.1772   | 0.50395   |             0.95314  | 1568 |            22 |          22 |
| T_reconstructed_quarterly | cpi       |         8 | -0.017437  | 0.20539  | 0.93249   |             0.95314  | 1522 |            22 |          22 |
| T_reconstructed_quarterly | cpi       |        12 | -0.10127   | 0.23879  | 0.67233   |             0.95314  | 1471 |            22 |          22 |
| W_CWY_annual              | gdp       |         0 | -0.10047   | 0.071665 | 0.17427   |             0.46456  |  654 |            32 |          34 |
| W_CWY_annual              | gdp       |         2 | -0.13048   | 0.17544  | 0.46456   |             0.46456  |  654 |            32 |          34 |
| W_CWY_annual              | gdp       |         5 | -0.24349   | 0.25379  | 0.34733   |             0.46456  |  654 |            32 |          34 |
| W_CWY_annual              | cpi       |         0 |  0.033377  | 0.12124  | 0.78554   |             0.78554  |  654 |            32 |          34 |
| W_CWY_annual              | cpi       |         2 | -0.11609   | 0.17933  | 0.5238    |             0.78554  |  654 |            32 |          34 |
| W_CWY_annual              | cpi       |         5 | -0.32224   | 0.26367  | 0.23403   |             0.5226   |  654 |            32 |          34 |
| W_external_USA_annual     | gdp       |         0 | -0.015132  | 0.06415  | 0.81538   |             0.81538  |  702 |            33 |           1 |
| W_external_USA_annual     | gdp       |         2 | -0.14706   | 0.19417  | 0.45618   |             0.59632  |  675 |            33 |           1 |
| W_external_USA_annual     | gdp       |         5 | -0.2574    | 0.24336  | 0.30222   |             0.59632  |  610 |            32 |           1 |
| W_external_USA_annual     | cpi       |         0 |  0.055467  | 0.055428 | 0.32619   |             0.99597  |  702 |            33 |           1 |
| W_external_USA_annual     | cpi       |         2 |  0.10673   | 0.15586  | 0.50004   |             0.99597  |  675 |            33 |           1 |
| W_external_USA_annual     | cpi       |         5 | -0.0013645 | 0.26714  | 0.99597   |             0.99597  |  610 |            32 |           1 |
| W_external_USA_quarterly  | gdp       |         0 |  0.044645  | 0.048476 | 0.35903   |             0.46673  | 2974 |            44 |           1 |
| W_external_USA_quarterly  | gdp       |         4 | -0.1707    | 0.12097  | 0.16107   |             0.43043  | 2851 |            39 |           1 |
| W_external_USA_quarterly  | gdp       |         8 | -0.1294    | 0.15554  | 0.40734   |             0.4814   | 2771 |            39 |           1 |
| W_external_USA_quarterly  | gdp       |        12 | -0.21735   | 0.14581  | 0.13917   |             0.43043  | 2665 |            33 |           1 |
| W_external_USA_quarterly  | cpi       |         0 | -0.0088492 | 0.028575 | 0.75737   |             0.86952  | 2970 |            43 |           1 |
| W_external_USA_quarterly  | cpi       |         4 | -0.089006  | 0.10545  | 0.40049   |             0.86952  | 2870 |            42 |           1 |
| W_external_USA_quarterly  | cpi       |         8 |  0.099     | 0.17467  | 0.57206   |             0.86952  | 2746 |            38 |           1 |
| W_external_USA_quarterly  | cpi       |        12 | -0.010117  | 0.17361  | 0.95365   |             0.95365  | 2656 |            37 |           1 |

Raw p-values are the main reported test statistics. BH q-values and restricted block-wild p-values are informational. Calendar score HAC preserves common monetary issuers and overlapping outcome windows. Few effective time blocks limit inference, especially at long horizons.

## Interpretation limits

The CWY world sample mixes identification methods and inherited shocks. Taylor innovations are a separate weaker identification class. External Fed/ECB models measure spillovers. Intraday US/ECB reconstructions retain their own units and vintages. None are spliced into a single artificial shock series.

No coefficient ranking or raw p-value identifies an expansionary monetary response on its own. The total conditional response and its uncertainty must be inspected; time effects absorb common shock main effects in external/currency-union panels.

## Recorded exclusions / failures

insufficient_observations       3387
insufficient_supported_panel      27
