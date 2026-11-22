# Chunk F01: General-government gross debt / GDP

Status: core country/panel/external specifications executed; Model E diagnostics executed where supported. This is exploratory research, not a causal finding about changing the characteristic itself.

Mechanism: Interest income to creditors versus debt-service, fiscal adjustment and risk-premium channels.

Theoretical direction: ambiguous; gamma>0 would mean less contraction / more price-level response as debt rises. No expected sign is treated as an empirical result.

Source / verified series: IMF WEO October 2026 / `GGXWDG_NGDP`.

Dating: only the prior calendar year's genuinely observed characteristic is used. Its native frequency remains annual in quarterly LPs. It is a predetermined exposure state, never an interpolated quarterly observation. Missing prior years are not filled.

Scaling: one unit of Z is 10.0 percent_of_GDP; centering is fixed at 50.0. The interaction is a change in the shock response per one unit of Z. A positive gamma does not by itself imply that the total GDP response is positive.

Identification concern: historical WEO estimates/revisions; debt is endogenous; one lag does not make Z exogenous.

Observed characteristic coverage: 226 economies, 1980–2025, 6784 country-year values. Effective LP support is in `coverage.csv` and differs by outcome and horizon.

Attempted specifications: 21948; estimated: 10987; failures: 0. Rank/variation/sample exclusions remain in the attempt log.

## Global interactions at prespecified horizons

| universe                  | outcome   |   horizon |   estimate |        se |      p_raw |   q_BH_informational |     n |   n_countries |   n_issuers |
|:--------------------------|:----------|----------:|-----------:|----------:|-----------:|---------------------:|------:|--------------:|------------:|
| H_BDY_daily               | gdp       |         0 |  0.018134  | 0.010633  | 0.091595   |            0.099228  |  2722 |            38 |          20 |
| H_BDY_daily               | gdp       |         4 |  0.07692   | 0.030328  | 0.012948   |            0.018703  |  2722 |            38 |          20 |
| H_BDY_daily               | gdp       |         8 |  0.10913   | 0.032047  | 0.00099302 |            0.0040388 |  2722 |            38 |          20 |
| H_BDY_daily               | gdp       |        12 |  0.08814   | 0.032778  | 0.0085555  |            0.013903  |  2672 |            38 |          20 |
| H_BDY_daily               | cpi       |         0 | -0.0064777 | 0.0038147 | 0.092988   |            0.77039   |  2585 |            36 |          18 |
| H_BDY_daily               | cpi       |         4 | -0.0072487 | 0.016777  | 0.66675    |            0.86395   |  2585 |            36 |          18 |
| H_BDY_daily               | cpi       |         8 |  0.015535  | 0.024275  | 0.52386    |            0.86395   |  2585 |            36 |          18 |
| H_BDY_daily               | cpi       |        12 |  0.01567   | 0.028381  | 0.58224    |            0.86395   |  2585 |            36 |          18 |
| H_ECB_reconstructed_2026  | gdp       |         0 | -0.017716  | 0.041351  | 0.66924    |            0.96669   |  1631 |            19 |           1 |
| H_ECB_reconstructed_2026  | gdp       |         4 | -0.0047313 | 0.095316  | 0.96051    |            0.99366   |  1555 |            19 |           1 |
| H_ECB_reconstructed_2026  | gdp       |         8 |  0.09668   | 0.084076  | 0.2531     |            0.6906    |  1479 |            19 |           1 |
| H_ECB_reconstructed_2026  | gdp       |        12 |  0.092263  | 0.082364  | 0.26561    |            0.6906    |  1403 |            19 |           1 |
| H_ECB_reconstructed_2026  | cpi       |         0 | -0.009964  | 0.009618  | 0.30255    |            0.89571   |  1740 |            20 |           1 |
| H_ECB_reconstructed_2026  | cpi       |         4 | -0.0089307 | 0.023335  | 0.70271    |            0.91352   |  1678 |            20 |           1 |
| H_ECB_reconstructed_2026  | cpi       |         8 |  0.012941  | 0.021856  | 0.55512    |            0.89571   |  1593 |            19 |           1 |
| H_ECB_reconstructed_2026  | cpi       |        12 | -0.044018  | 0.04627   | 0.34383    |            0.89571   |  1517 |            19 |           1 |
| T_reconstructed_annual_1L | gdp       |         0 |  0.0062379 | 0.020789  | 0.76554    |            0.76554   |  2094 |            84 |          84 |
| T_reconstructed_annual_1L | gdp       |         2 | -0.040753  | 0.062097  | 0.51522    |            0.76554   |  1987 |            84 |          84 |
| T_reconstructed_annual_1L | gdp       |         5 | -0.12117   | 0.06607   | 0.074296   |            0.44578   |  1804 |            84 |          84 |
| T_reconstructed_annual_1L | cpi       |         0 |  0.054964  | 0.041525  | 0.19246    |            0.53198   |  2088 |            84 |          84 |
| T_reconstructed_annual_1L | cpi       |         2 |  0.031076  | 0.055771  | 0.58035    |            0.58035   |  1969 |            84 |          84 |
| T_reconstructed_annual_1L | cpi       |         5 | -0.080694  | 0.069533  | 0.25289    |            0.53198   |  1769 |            84 |          84 |
| T_reconstructed_quarterly | gdp       |         0 |  0.0029809 | 0.019046  | 0.87581    |            0.87581   |  4656 |            50 |          50 |
| T_reconstructed_quarterly | gdp       |         4 |  0.045567  | 0.026648  | 0.089024   |            0.24176   |  4497 |            50 |          50 |
| T_reconstructed_quarterly | gdp       |         8 |  0.03663   | 0.032863  | 0.26655    |            0.31502   |  4317 |            50 |          50 |
| T_reconstructed_quarterly | gdp       |        12 |  0.06461   | 0.038004  | 0.090953   |            0.24176   |  4133 |            50 |          50 |
| T_reconstructed_quarterly | cpi       |         0 |  0.021961  | 0.02065   | 0.28897    |            0.67775   |  4685 |            50 |          50 |
| T_reconstructed_quarterly | cpi       |         4 |  0.019681  | 0.038028  | 0.60543    |            0.67775   |  4597 |            50 |          50 |
| T_reconstructed_quarterly | cpi       |         8 |  0.037194  | 0.057203  | 0.51642    |            0.67775   |  4439 |            50 |          50 |
| T_reconstructed_quarterly | cpi       |        12 |  0.039575  | 0.074597  | 0.59645    |            0.67775   |  4259 |            50 |          50 |
| W_CWY_annual              | gdp       |         0 | -0.0063111 | 0.03185   | 0.84398    |            0.84398   |  3829 |           165 |          87 |
| W_CWY_annual              | gdp       |         2 | -0.063127  | 0.077535  | 0.42062    |            0.50474   |  3827 |           165 |          87 |
| W_CWY_annual              | gdp       |         5 | -0.25936   | 0.15934   | 0.11186    |            0.2238    |  3817 |           164 |          87 |
| W_CWY_annual              | cpi       |         0 | -0.022676  | 0.033055  | 0.49687    |            0.97459   |  3661 |           163 |          87 |
| W_CWY_annual              | cpi       |         2 | -0.010745  | 0.11084   | 0.92328    |            0.97459   |  3649 |           163 |          87 |
| W_CWY_annual              | cpi       |         5 | -0.10843   | 0.15684   | 0.49357    |            0.97459   |  3619 |           162 |          87 |
| W_external_USA_annual     | gdp       |         0 |  0.022814  | 0.040786  | 0.5807     |            0.5807    |  4785 |           188 |           1 |
| W_external_USA_annual     | gdp       |         2 | -0.13265   | 0.046012  | 0.0081829  |            0.049097  |  4411 |           188 |           1 |
| W_external_USA_annual     | gdp       |         5 | -0.064232  | 0.069388  | 0.36512    |            0.45483   |  3839 |           186 |           1 |
| W_external_USA_annual     | cpi       |         0 | -0.1269    | 0.07565   | 0.10545    |            0.40533   |  4483 |           181 |           1 |
| W_external_USA_annual     | cpi       |         2 | -0.27149   | 0.20728   | 0.20266    |            0.40533   |  4119 |           181 |           1 |
| W_external_USA_annual     | cpi       |         5 | -0.069525  | 0.099621  | 0.4929     |            0.59148   |  3569 |           180 |           1 |
| W_external_USA_quarterly  | gdp       |         0 | -0.02979   | 0.024155  | 0.22001    |            0.28602   |  8600 |           105 |           1 |
| W_external_USA_quarterly  | gdp       |         4 | -0.045911  | 0.043801  | 0.29686    |            0.35083   |  8175 |           104 |           1 |
| W_external_USA_quarterly  | gdp       |         8 | -0.10917   | 0.065607  | 0.099071   |            0.18399   |  7749 |           102 |           1 |
| W_external_USA_quarterly  | gdp       |        12 | -0.16332   | 0.091202  | 0.076305   |            0.18399   |  7327 |           100 |           1 |
| W_external_USA_quarterly  | cpi       |         0 | -0.0092894 | 0.011951  | 0.43859    |            0.57444   | 18132 |           178 |           1 |
| W_external_USA_quarterly  | cpi       |         4 | -0.079416  | 0.055086  | 0.15224    |            0.53338   | 17395 |           177 |           1 |
| W_external_USA_quarterly  | cpi       |         8 | -0.071645  | 0.081122  | 0.37914    |            0.57444   | 16668 |           176 |           1 |
| W_external_USA_quarterly  | cpi       |        12 |  0.036431  | 0.053973  | 0.50122    |            0.57444   | 15948 |           176 |           1 |

Raw p-values are the main reported test statistics. BH q-values and restricted block-wild p-values are informational. Calendar score HAC preserves common monetary issuers and overlapping outcome windows. Few effective time blocks limit inference, especially at long horizons.

## Interpretation limits

The CWY world sample mixes identification methods and inherited shocks. Taylor innovations are a separate weaker identification class. External Fed/ECB models measure spillovers. Intraday US/ECB reconstructions retain their own units and vintages. None are spliced into a single artificial shock series.

No coefficient ranking or raw p-value identifies an expansionary monetary response on its own. The total conditional response and its uncertainty must be inspected; time effects absorb common shock main effects in external/currency-union panels.

## Recorded exclusions / failures

insufficient_observations           10948
insufficient_moderator_variation       13
