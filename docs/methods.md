# Estimation notes

The analysis follows country-quarter observations through the monetary shock and the subsequent macroeconomic response. Local projections provide the direct estimates; a panel VARX supplies a comparison under a finite dynamic law. Both use the published high-frequency shocks as monetary inputs.

## Timing and the ownership comparison

Country calendars remain complete when constructing leads and lags. Sample restrictions are applied afterwards, so dropping an ineligible shock quarter does not shorten a lag or move a future outcome to an earlier date. Creditor stocks use the preceding quarter's observation where available and otherwise the previous year's annual row. Source, date, frequency, issuer sector, valuation and portfolio are retained with the observations.

Own-policy shocks come from Bolhuis–Das–Yao. The separate euro-area design uses Jarociński–Karadi and its ECB update; comparisons that pool the euro area with other issuers use Bolhuis for every issuer. A positive unit is a ten-basis-point surprise in the source's market instrument. The swap reference and market depth differ across issuers; instrument details are in `data/monetary_instruments.csv`.

Write public debt, in percentage points of GDP, as

$$D=P+C+F,$$

where $P$ denotes resident holdings outside the central bank, $C$ central-bank holdings and $F$ foreign holdings. At fixed $D$ and $C$, increasing $P$ has an equal foreign counterpart. The ownership coefficient therefore describes a reallocation across creditors at a given total debt ratio.

The refinancing share $r$ is principal due within one year divided by outstanding principal in the same portfolio. The common reference, $\bar r$, is the median on the eligible euro-area predictor support, about 0.1691. The model uses $(r-\bar r)/0.10$. Its six focal regressors are the monetary surprise multiplied by $D/10$, $P/10$, $C/10$ and the interaction of each state with centered refinancing. These six regressors remain unpenalized.

For outcomes in $100\log$ levels, the local-projection dependent variable is $y_{i,t+h}-y_{i,t-1}$, for $h=0,\ldots,12$. The coefficient on the ownership regressor is the response gradient at reference refinancing; its refinancing interaction changes that gradient for a ten-percentage-point rise in the share due within one year. Principal redemption and coupon resetting can occur on different dates. The product $rP$ alone does not reveal which creditors hold the instruments being refinanced or repriced, hence the separate contract calculation and allocation bounds.

## Controls and post-double-selection

The mandatory controls include source-regime and calendar-quarter effects, country seasonality, source-specific monetary and information slopes, state levels and their information interactions, four growth and inflation lags, and predetermined macroeconomic conditions. Available euro-area fiscal balances, interest expenditure and unemployment also enter. An issuer's own monetary authority is excluded from its foreign-policy controls.

The optional dictionary adds lagged shock-state products, business-cycle and macro-state interactions, and Fed/ECB spillover interactions. Minimal, full and PDS estimates use the same observations for each outcome and horizon. PDS chooses from the optional dictionary after projecting the mandatory core out of the outcome, controls and six focal regressors. It takes the union of controls selected for the outcome and for each focal regressor, then refits the equation by least squares. In the 132 native cases this union contains 0–8 optional controls, averaging 2.9.

`selection.py` standardizes the residual control columns and the target. With $p$ optional controls, its weighted LASSO objective is

$$\frac{\|y-Zb\|^2}{2N}+\frac{1.1q}{N}\sum_j\ell_j|b_j|,$$

where $q=\Phi^{-1}(1-\gamma/(2p))$ and $\gamma=0.1/\log(T)$. Each loading $\ell_j$ is the square root of the unnormalized, centered Bartlett(12) covariance of regressor-residual scores summed by calendar quarter, including finite-rank scaling. The loading is of order $\sqrt N$ under weak dependence, so the effective penalty is of order $1/\sqrt N$. Initial residuals come from the five most correlated residual controls; three loading updates use post-LASSO residuals.

`lasso.py` absorbs the loadings into the columns and solves the resulting common-penalty problem by coordinate descent. For $G=X'X/N$ and $a=X'y/N$, the update is

$$b_j\leftarrow\frac{S(a_j-\sum_{k\ne j}G_{jk}b_k,\alpha)}{G_{jj}},\qquad S(v,\alpha)=\operatorname{sign}(v)\max(|v|-\alpha,0).$$

The solver maintains the residual gradient and checks both the primal-dual gap and the KKT conditions. Failure to converge raises an error.

## Least squares and uncertainty

A pivoted QR decomposition supplies a basis $Q$ for the nuisance controls. Residualization uses $X-Q(Q'X)$, avoiding an $N$-by-$N$ projection matrix. For the residualized focal matrix $Z$ and outcome $y_r$, the calculation is

$$B=(Z'Z)^{-1},\qquad \hat\beta=BZ'y_r,\qquad u=y_r-Z\hat\beta.$$

The code checks the nuisance rank and the singular values of $Z$. Degrees of freedom use the rank of the complete design. NumPy supplies array operations and SciPy supplies decompositions and distribution functions; the regression calculations are explicit in `local_projection.py`.

Inference starts from calendar-quarter score sums, $s_t=\sum_i Z_{it}u_{it}$. Empty quarters within the estimation interval retain zero scores. The covariance is

$$B\left[\sum_t s_ts_t'+\sum_{l=1}^{12}(1-l/13)\sum_t(s_ts_{t-l}'+s_{t-l}s_t')\right]B,$$

with finite-sample factor $[T/(T-1)][(N-1)/(N-\mathrm{rank})]$. Pointwise probabilities use $T-1$ reference degrees of freedom. Summing scores within a quarter allows contemporaneous dependence across countries; the twelve Bartlett lags account for serial dependence and overlapping response windows.

For joint inference, each Gaussian multiplier is the sum of thirteen successive independent standard-normal draws divided by $\sqrt{13}$. Its autocovariance matches Bartlett(12). Scores are aligned across settings, horizons and outcomes before drawing 99,999 realizations of the maximum absolute studentized statistic. Selection is held fixed during these simulations.

| PDS or VARX family | Contrasts |
|---|---:|
| Reporting horizons: two outcomes, two margins, three settings at h=4,8,12, plus twelve AE–EM differences | 48 |
| Complete LP curves: h=0,…,12, plus the same twelve reporting-horizon differences | 168 |
| Debt, REER and debt accumulation | 90 |
| Forced foreign-policy slopes | 36 |
| VARX curves and reporting-horizon group differences | 252 |
| External-exposure extension and early group differences | 36 |

The full-control benchmarks also retain their families of 48, 168 and 90 contrasts, together with 36 policy-aggregation, 36 creditor-sector and eighteen ownership-only contrasts. There are 1,026 overlapping family memberships across the analysis. Adjustment is within each reported family; it is not a global correction across estimators. In particular, the 168-member family includes every quarterly horizon but adds AE–EM differences only at the three reporting horizons.

A country wild bootstrap provides a separate dependence check for the primary PDS price interaction at h=1,2,4. It imposes the focal null and fixes the selected controls, enumerating all $2^{11-1}=1,024$ Rademacher patterns and using 9,999 six-point Webb draws. This calculation assumes independence across country clusters, whereas the calendar-score covariance permits dependence across countries within a quarter.

## Dynamic comparison and external exposures

The panel VARX contains quarterly changes in GDP, consumer prices and REER, all measured in $100\log$ units. Four lags of all three variables and the six current fiscal exposures are unpenalized. PDS forms a common optional-control union from the three outcome equations and the eighteen unpenalized-regressor equations. `panel_var.py` then solves the multivariate least-squares system.

Writing the impact matrix as $B$, responses follow

$$\Psi_0=B,\qquad\Psi_h=\sum_{l=1}^{\min(4,h)}A_l\Psi_{h-l}.$$

Summing these responses gives the level gradient. Future fiscal states and further exogenous innovations are held fixed. The companion matrix is checked for stability; stacked multiequation scores give the joint HAC covariance, and complex-step differentiation gives the delta-method Jacobian. Matched direct projections use the same 1,273 euro-area, 728 advanced and 403 emerging observations.

The external-exposure extension adds two unpenalized monetary slopes: the previous year's foreign-currency public-debt share per ten percentage points, and the predetermined current-account deficit per five points of GDP. Their levels and information interactions are mandatory; two lags of the new products enter the optional dictionary. The deficit columns replace identical current-account columns without changing their span.

Currency shares come from the Arslanalp–Tsuda annual tables, with DGM histories for Japan, Norway and New Zealand. The advanced IMF table covers government debt securities and the emerging table general-government gross debt. A country keeps one source, chosen by coverage over 1999–2021 and then the endpoint. The extension retains all 728 advanced and 403 emerging observations; the BIS C4 long-term-bond comparison has its own matched sample.

The 36-contrast extension contains five quantities at h=1,2,4 in each group: the baseline interaction, augmented interaction, their difference, the currency slope and the deficit slope. Six AE–EM differences complete the family. Aligned influence scores supply the covariance of changes and group differences. Conditioning on these exposures tests possible explanations for the gradient; it does not estimate causal mediation.

## Checks and sample coverage

`engine_validation.py` compares coordinate descent with the orthogonal LASSO solution and an independently coded proximal-gradient solver. For 54 actual regression designs it also compares focal coefficients with full-design SVD and recomputes the covariance using a dense Bartlett kernel. `numerical_validation.py` checks known-coefficient selection, target rescaling, direct VARX simulation and finite-difference derivatives.

`verify_results.py` checks source hashes, debt identities, observation dates, complete calendars, ranks, convergence, covariance matrices, family sizes and sample equality. Results of these checks, including numerical discrepancies, are written under `results/`.

The coverage figure uses the observation keys for the one-year GDP projection, h=4. There are 1,493 euro-area, 728 advanced and 403 emerging observations. Navy identifies preceding-quarter ownership measurements; gold identifies previous-year annual states. White cells are excluded from this particular projection and can reflect missing inputs, required lags or leads, or eligibility rules. The shaded own-policy tail starts after 2022Q1 because the global-policy controls require complete Fed and ECB shock quarters. The separate euro-area model has later ECB coverage. Other outcomes and horizons have their own samples.
