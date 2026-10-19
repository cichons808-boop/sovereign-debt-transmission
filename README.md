# Creditor Residence, Refinancing, and Monetary Transmission

Szymon Cichoń · University of Economics in Katowice

Data and estimation code accompanying the article. The question is whether monetary transmission depends on who holds public debt, particularly when a larger share of principal is due for refinancing. The ownership comparison reallocates claims from foreign investors to resident holders outside the central bank, at a given debt ratio and central-bank position.

The quarterly analysis covers nineteen euro-area countries, eleven advanced economies with their own monetary policy and eight emerging economies. It uses published monetary and information surprises from Bolhuis–Das–Yao and Jarociński–Karadi, together with creditor stocks, repayment schedules and macroeconomic series. The clearest finding is an early positive price interaction in advanced own-policy economies. Output estimates vary more across propagation models; the other monetary settings and the fiscal and exchange-rate extensions give a less uniform picture.

## Reproducing the results

The reference environment is Python 3.12. From the extracted directory containing `run.py`, run:

```
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py all
```

On Windows, use `.venv\Scripts\activate` in Command Prompt to activate the environment. Installation needs an internet connection; the calculations then use the source files supplied here. LaTeX and API credentials are not needed. Instructions in Polish are in [INSTRUKCJA.txt](INSTRUKCJA.txt).

A complete run rebuilds the quarterly panels, estimates the models, calculates inference and produces the tables and figures. It ends with a check of the data and numerical results. For work on a particular stage, the same sequence can be run separately:

```
python run.py data
python run.py estimate
python run.py exhibits
python run.py check
```

Each stage uses the preceding stage's files. For example, after editing a figure, rerun `exhibits`; after changing a model, rerun `estimate`, `exhibits` and `check`. Errors stop execution. Seeds and numerical thread counts are set by the program.

## Data and output

Original workbooks, series and source reports are in `data/raw/`. The catalogue, `data/sources.csv`, records the addresses, identifiers and SHA256 checksums of 404 source files. Macro-series choices and monetary-instrument definitions are recorded separately in `data/macro_sources.json` and `data/monetary_instruments.csv`. Source attribution and data definitions should be retained when reusing the material.

`data/processed/` contains the transformed observations and quarterly panels. The `data` stage reconstructs these files from the originals. Annual creditor observations keep their annual dates and frequency labels; the quarterly macroeconomic outcomes retain their observed frequency.

Execution creates two additional directories. `results/` holds coefficient estimates, covariance matrices, selected controls, observation keys and inference. `output/` holds the LaTeX tables and vector PDF figures. Both are excluded from Git by the supplied `.gitignore`, as are the virtual environment and Python cache files. The article is distributed separately.

The main direct projections are in `results/ml_lp.csv`, with their complete records in `results/ml_lp.json`. The corresponding VARX files are `ml_var.csv/json`; `ml_var_matched_lp.csv/json` contains the direct estimates on the VARX sample. Simultaneous LP inference is in `ml_simultaneous.csv/json`. Additional estimates cover debt accumulation, creditor sectors, policy-block weighting, country omissions, external exposures and the Belgian, Portuguese and Polish institutional evidence. Null and imprecise estimates are included in the output.

## Reading the code

`run.py` gives the execution order. Data preparation starts in `src/prepare_data.py`. Model choices are stored under `config/`; the equations, penalty normalization and inference families are described in [docs/methods.md](docs/methods.md), and the variable definitions in [docs/variables.md](docs/variables.md).

The direct projections use `local_projection.py`. `selection.py` adds post-double-selection, calling the coordinate-descent solver in `lasso.py`. `panel_var.py` estimates the multivariate system and propagates its responses. These routines use NumPy arrays and SciPy decompositions and distribution functions; the regression and selection algorithms are written out in the source.

For inference, start with `simultaneous_inference.py` and `primary_inference.py`. The former constructs joint bands from calendar-aligned scores; the latter contains the country wild bootstrap and average monetary-response derivatives. `mechanisms.py` estimates the currency-denomination and current-account extensions on matched observations. The full-control benchmarks start in `specification.py`; `retail_episodes.py` contains the monthly institutional calculations.

The final check writes `results/verification.json`. More detailed numerical comparisons appear in `results/engine_validation.json` and `results/ml_validation.json`: these compare the estimators with full-design SVD, an independently coded LASSO solver, a dense HAC calculation and direct VARX simulation.
