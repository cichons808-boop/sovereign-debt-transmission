# Chunk E01: Net energy imports / energy use

Status: core country/panel/external specifications executed; Model E diagnostics executed where supported. This is exploratory research, not a causal finding about changing the characteristic itself.

Mechanism: Energy import costs, currency adjustment and supply sensitivity.

Theoretical direction: ambiguous. No expected sign is treated as an empirical result.

Source / verified series: World Bank WDI / IEA / `EG.IMP.CONS.ZS`.

Dating: only the prior calendar year's genuinely observed characteristic is used. Its native frequency remains annual in quarterly LPs. It is a predetermined exposure state, never an interpolated quarterly observation. Missing prior years are not filled.

Scaling: one unit of Z is 10.0 percent_of_energy_use; centering is fixed at 0.0. The interaction is a change in the shock response per one unit of Z. A positive gamma does not by itself imply that the total GDP response is positive.

Identification concern: not a monetary-policy-specific exposure; net exporters have negative values; global energy shocks.

Observed characteristic coverage: 188 economies, 1990–2024, 6016 country-year values. Effective LP support is in `coverage.csv` and differs by outcome and horizon.

Attempted specifications: 15302; estimated: 10829; failures: 0. Rank/variation/sample exclusions remain in the attempt log.

## Global interactions at prespecified horizons

| universe                  | outcome   |   horizon |    estimate |         se |    p_raw |   q_BH_informational |     n |   n_countries |   n_issuers |
|:--------------------------|:----------|----------:|------------:|-----------:|---------:|---------------------:|------:|--------------:|------------:|
| H_BDY_daily               | gdp       |         0 |  0.0028222  | 0.0020352  | 0.16899  |              0.59933 |  2718 |            38 |          20 |
| H_BDY_daily               | gdp       |         4 |  0.0017287  | 0.0023275  | 0.45959  |              0.59933 |  2718 |            38 |          20 |
| H_BDY_daily               | gdp       |         8 | -0.00085507 | 0.0024574  | 0.7287   |              0.73823 |  2718 |            38 |          20 |
| H_BDY_daily               | gdp       |        12 |  0.0026735  | 0.0027424  | 0.33226  |              0.59933 |  2668 |            38 |          20 |
| H_BDY_daily               | cpi       |         0 |  0.00062083 | 0.0012512  | 0.62098  |              0.99554 |  2581 |            36 |          18 |
| H_BDY_daily               | cpi       |         4 |  0.0017708  | 0.0025121  | 0.48271  |              0.99554 |  2581 |            36 |          18 |
| H_BDY_daily               | cpi       |         8 |  0.0002108  | 0.0035622  | 0.95294  |              0.99554 |  2581 |            36 |          18 |
| H_BDY_daily               | cpi       |        12 |  0.00046476 | 0.0052356  | 0.92947  |              0.99554 |  2581 |            36 |          18 |
| H_ECB_reconstructed_2026  | gdp       |         0 | -0.0052822  | 0.010595   | 0.61917  |              0.90643 |  1575 |            19 |           1 |
| H_ECB_reconstructed_2026  | gdp       |         4 | -0.019507   | 0.026966   | 0.47115  |              0.90643 |  1502 |            19 |           1 |
| H_ECB_reconstructed_2026  | gdp       |         8 |  0.0024761  | 0.028025   | 0.92978  |              0.92978 |  1427 |            19 |           1 |
| H_ECB_reconstructed_2026  | gdp       |        12 |  0.0082336  | 0.036019   | 0.81971  |              0.92978 |  1351 |            19 |           1 |
| H_ECB_reconstructed_2026  | cpi       |         0 | -0.0023177  | 0.0069838  | 0.74065  |              0.79081 |  1644 |            20 |           1 |
| H_ECB_reconstructed_2026  | cpi       |         4 | -0.0056079  | 0.016722   | 0.73803  |              0.79081 |  1622 |            20 |           1 |
| H_ECB_reconstructed_2026  | cpi       |         8 | -0.019376   | 0.016671   | 0.24791  |              0.64457 |  1538 |            19 |           1 |
| H_ECB_reconstructed_2026  | cpi       |        12 | -0.047398   | 0.023602   | 0.047429 |              0.15414 |  1465 |            19 |           1 |
| T_reconstructed_annual_1L | gdp       |         0 |  0.0052871  | 0.0050336  | 0.30095  |              0.36115 |  1727 |            70 |          70 |
| T_reconstructed_annual_1L | gdp       |         2 | -0.028688   | 0.02629    | 0.28333  |              0.36115 |  1635 |            70 |          70 |
| T_reconstructed_annual_1L | gdp       |         5 | -0.026035   | 0.017608   | 0.15002  |              0.36115 |  1482 |            70 |          70 |
| T_reconstructed_annual_1L | cpi       |         0 |  0.002435   | 0.005083   | 0.63497  |              0.89376 |  1723 |            70 |          70 |
| T_reconstructed_annual_1L | cpi       |         2 | -0.0071863  | 0.021888   | 0.7448   |              0.89376 |  1626 |            70 |          70 |
| T_reconstructed_annual_1L | cpi       |         5 | -0.017779   | 0.026148   | 0.50193  |              0.89376 |  1464 |            70 |          70 |
| T_reconstructed_quarterly | gdp       |         0 |  0.0022687  | 0.0018122  | 0.2127   |              0.55303 |  4303 |            46 |          46 |
| T_reconstructed_quarterly | gdp       |         4 |  0.0029055  | 0.0022368  | 0.19614  |              0.55303 |  4191 |            46 |          46 |
| T_reconstructed_quarterly | gdp       |         8 |  0.0020722  | 0.00279    | 0.45896  |              0.83519 |  4027 |            46 |          46 |
| T_reconstructed_quarterly | gdp       |        12 |  0.0012269  | 0.0034804  | 0.72502  |              0.83519 |  3859 |            46 |          46 |
| T_reconstructed_quarterly | cpi       |         0 |  0.0015127  | 0.00077655 | 0.05344  |              0.69472 |  4315 |            46 |          46 |
| T_reconstructed_quarterly | cpi       |         4 | -0.0005694  | 0.0029296  | 0.84618  |              0.9167  |  4283 |            46 |          46 |
| T_reconstructed_quarterly | cpi       |         8 | -0.001278   | 0.0043049  | 0.76703  |              0.9167  |  4136 |            46 |          46 |
| T_reconstructed_quarterly | cpi       |        12 | -0.0017388  | 0.0062898  | 0.78264  |              0.9167  |  3972 |            46 |          46 |
| W_CWY_annual              | gdp       |         0 | -0.0003829  | 0.0033294  | 0.90926  |              0.90926 |  3201 |           126 |          80 |
| W_CWY_annual              | gdp       |         2 | -0.0013369  | 0.0085225  | 0.87648  |              0.90926 |  3201 |           126 |          80 |
| W_CWY_annual              | gdp       |         5 |  0.014124   | 0.016183   | 0.39023  |              0.58534 |  3198 |           126 |          80 |
| W_CWY_annual              | cpi       |         0 |  0.021953   | 0.011339   | 0.063022 |              0.1747  |  3048 |           124 |          80 |
| W_CWY_annual              | cpi       |         2 |  0.045395   | 0.027203   | 0.10631  |              0.1747  |  3036 |           124 |          80 |
| W_CWY_annual              | cpi       |         5 |  0.035972   | 0.02583    | 0.1747   |              0.1747  |  3011 |           123 |          80 |
| W_external_USA_annual     | gdp       |         0 |  0.0005789  | 0.0089598  | 0.94898  |              0.94898 |  3522 |           137 |           1 |
| W_external_USA_annual     | gdp       |         2 | -0.028553   | 0.02939    | 0.34099  |              0.64027 |  3246 |           136 |           1 |
| W_external_USA_annual     | gdp       |         5 | -0.034283   | 0.044272   | 0.44734  |              0.64027 |  2844 |           136 |           1 |
| W_external_USA_annual     | cpi       |         0 | -0.0033562  | 0.0081594  | 0.6842   |              0.89417 |  3332 |           134 |           1 |
| W_external_USA_annual     | cpi       |         2 | -0.0041678  | 0.031      | 0.89417  |              0.89417 |  3057 |           133 |           1 |
| W_external_USA_annual     | cpi       |         5 | -0.030476   | 0.022032   | 0.18113  |              0.89417 |  2644 |           131 |           1 |
| W_external_USA_quarterly  | gdp       |         0 |  0.0088828  | 0.0040975  | 0.032304 |              0.11417 |  7824 |            94 |           1 |
| W_external_USA_quarterly  | gdp       |         4 |  0.017537   | 0.0082209  | 0.03513  |              0.11417 |  7523 |            93 |           1 |
| W_external_USA_quarterly  | gdp       |         8 |  0.01696    | 0.014226   | 0.23585  |              0.28963 |  7142 |            91 |           1 |
| W_external_USA_quarterly  | gdp       |        12 |  0.024451   | 0.019797   | 0.21964  |              0.28963 |  6764 |            89 |           1 |
| W_external_USA_quarterly  | cpi       |         0 |  0.0048834  | 0.002536   | 0.056707 |              0.14744 | 13575 |           137 |           1 |
| W_external_USA_quarterly  | cpi       |         4 |  0.015415   | 0.0073583  | 0.038476 |              0.14744 | 13343 |           137 |           1 |
| W_external_USA_quarterly  | cpi       |         8 |  0.017089   | 0.012686   | 0.18084  |              0.22634 | 12790 |           137 |           1 |
| W_external_USA_quarterly  | cpi       |        12 |  0.016198   | 0.017443   | 0.35527  |              0.35527 | 12240 |           137 |           1 |

Raw p-values are the main reported test statistics. BH q-values and restricted block-wild p-values are informational. Calendar score HAC preserves common monetary issuers and overlapping outcome windows. Few effective time blocks limit inference, especially at long horizons.

## Interpretation limits

The CWY world sample mixes identification methods and inherited shocks. Taylor innovations are a separate weaker identification class. External Fed/ECB models measure spillovers. Intraday US/ECB reconstructions retain their own units and vintages. None are spliced into a single artificial shock series.

No coefficient ranking or raw p-value identifies an expansionary monetary response on its own. The total conditional response and its uncertainty must be inspected; time effects absorb common shock main effects in external/currency-union panels.

## Recorded exclusions / failures

insufficient_observations       4371
insufficient_supported_panel      93
insufficient_shock_variation       9
