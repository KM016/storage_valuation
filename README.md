# Natural Gas Forecasting and Storage Valuation

An end to end quantitative research project linking point in time natural gas forecasts with an inventory constrained storage decision model.

> Personal Project<br>
> Date: 08/2026

## Project overview

This project builds on the forecasting and storage ideas I first encountered during the J.P. Morgan Quantitative Research Job Simulation. The original submissions remain unchanged. This is a separate personal project using a longer price series, archived EIA forecast vintages and a month by month storage model.

The research asks two questions:

1. Can storage and weather forecasts available at the time improve a 12 month Henry Hub price forecast?
2. Does lower average price error produce a more useful storage schedule?

The complete analysis is in [gas_storage_valuation.ipynb](gas_storage_valuation.ipynb). The storage output is a decision value based on the forecast and stated assumptions, not an arbitrage free price from a traded forward curve.

## Data

The project uses two fixed public data snapshots:

- realised monthly [Henry Hub spot prices](https://fred.stlouisfed.org/series/MHHNGSP), published by the EIA and downloaded through FRED;
- archived July editions of the [EIA Short Term Energy Outlook](https://www.eia.gov/outlooks/steo/outlook.php) from 2017 to 2026.

Each archived vintage contains the information published for that historical forecast year:

| Variable | EIA series | Use |
| --- | --- | --- |
| Henry Hub price | `NGHHUUS` | point in time training series and external EIA forecast benchmark |
| Working gas inventory | `NGWGPUS` | storage surplus feature |
| Heating degree days | `ZWHDPUS` | forecast heating demand |
| Cooling degree days | `ZWCDPUS` | forecast cooling demand |

The EIA's future Henry Hub forecast is never used as an input for predicting Henry Hub. It is retained only as an external benchmark and valuation scenario.

The notebook uses the committed data snapshot directly, so the extraction script is not required for a normal run. I used Codex to automate the creation of [extract_steo_vintages.py](extract_steo_vintages.py) as a reproducibility tool. It downloads each workbook listed in the manifest, verifies its SHA256 checksum and recreates the committed CSV. Full source definitions, units, retrieval dates and checksums are in [data/README.md](data/README.md).

## Point in time forecast design

A July STEO release contains historical or estimated data through June and forecasts from July onwards. Every historical forecast follows the same sequence:

1. use only vintage files released by that forecast year;
2. build the latest historical panel available at that date;
3. fit the model through June;
4. use that vintage's forecast storage, HDD and CDD paths;
5. forecast internally from July to the following July;
6. discard the first July forecast; and
7. score the 12 months from August to July.

Using the completed July price at a July forecast date would introduce one month of look ahead leakage. Storage averages and feature scaling are also estimated from training rows only.

Seven forecast years from July 2017 to July 2023 are used for development. July 2024 and July 2025 are later evaluations, and the July 2026 vintage produces the current forecast scenarios.

## Forecasting approach

The notebook uses ADF testing and ACF/PACF plots to examine the log price level and its first two differences. On the exact point in time history used for the first development forecast year, the level ADF p-value is 0.525, so I cannot reject the null hypothesis that the series has a unit root. After first differencing, the p-value falls to approximately 1.74 × 10⁻¹⁰, so I reject that null hypothesis for the differenced series. I therefore include first differenced models in the comparison, but the test does not select the final forecasting model by itself.

The model comparison includes:

- last price and seasonal naive baselines;
- the published EIA Henry Hub forecast;
- price only ARIMA and SARIMA level models;
- ARIMAX and SARIMAX level models using storage surplus, HDD and CDD;
- a level model sensitivity using weather deviations from normal;
- low order no drift ARIMA and ARIMAX models with `d = 1`; and
- a no drift seasonal fundamentals model with `d = 1`.

The differenced candidates have no drift because the price plot does not support a deterministic long term trend. All statistical models use log prices. Exponentiating the central log forecast gives a conditional median dollar price path rather than a bias corrected expected price.

ARIMA `(0,1,0)` without drift produces the same central forecast as carrying the latest observed price forward. I therefore retain the simpler last price baseline rather than duplicate it as a price only statistical model.

MAE across all 84 development forecasts is the stated selection measure. RMSE, median annual MAE, interval coverage, performance by forecast year and checks where one year is left out are reported alongside it.

## Forecasting results

### Development forecast years: July 2017 to July 2023

| Model | Pooled MAE | Median annual MAE | RMSE | 95% interval coverage |
| --- | ---: | ---: | ---: | ---: |
| **ARIMAX + storage, HDD and CDD** | **0.890** | 0.656 | **1.322** | 77.4% |
| Seasonal SARIMAX + same inputs | 0.913 | 0.646 | 1.335 | 76.2% |
| ARIMAX + weather deviations | 0.926 | 0.721 | 1.363 | 73.8% |
| ARIMA `(1,0,0)` | 1.005 | 0.729 | 1.462 | 78.6% |
| SARIMA `(1,0,0) × (1,0,0,12)` | 1.013 | 0.730 | 1.469 | 78.6% |
| EIA STEO forecast | 1.033 | 0.648 | 1.532 | N/A |
| ARIMAX `(1,1,1)` + fundamentals | 1.086 | 0.548 | 1.641 | 75.0% |
| ARIMAX `(0,1,0)` + fundamentals | 1.121 | **0.405** | 1.812 | 86.9% |
| Last price baseline | 1.266 | 0.483 | 2.013 | N/A |
| Seasonal naive baseline | 1.520 | 1.004 | 2.247 | N/A |

The level ARIMAX has the lowest pooled MAE and RMSE, so it is retained under the stated selection rule. Adding an annual seasonal error term does not improve either the price only or fundamentals model. The seasonal shape in the selected forecast instead enters through storage, HDD and CDD.

The differencing result is less clear. ARIMAX `(1,1,1)` is the strongest `d = 1` model on pooled MAE, and several differenced models perform better in calmer years. The selected model remains best in six of seven checks where one year is left out. When the 2022 forecast year is removed, ARIMAX `(0,1,0)` with fundamentals becomes best, with MAE 0.739 compared with 0.796 for the selected model.

The selected model also beats the last price baseline in only four of seven individual years. Its pooled advantage is therefore partly linked to its smaller error during the 2022 reversal rather than universal dominance across the forecast years.

### Later evaluations

| Model | July 2024 MAE | July 2025 MAE | July 2025 RMSE |
| --- | ---: | ---: | ---: |
| Selected level ARIMAX | 0.757 | 0.663 | 1.355 |
| ARIMAX `(1,1,1)` + fundamentals | 0.756 | **0.656** | 1.347 |
| ARIMAX `(0,1,0)` + fundamentals | 0.719 | 0.659 | 1.260 |
| Seasonal SARIMAX + fundamentals | 0.757 | 0.681 | 1.373 |
| Price only ARIMA | 0.616 | 0.685 | 1.424 |
| Price only SARIMA | 0.583 | 0.696 | 1.444 |
| EIA STEO forecast | **0.568** | 0.846 | **1.095** |

EIA has the lowest MAE in 2024. A differenced fundamentals model is slightly ahead in 2025, although EIA has the lowest RMSE because it gets closer to the large January 2026 price spike. These later periods are reported as robustness checks and are not used to reopen model selection.

The selected model's nominal 95% intervals cover only 77.4% of development observations. They condition on the archived EIA input paths and do not fully represent weather, supply or geopolitical shock risk.

## July 2026 forecast scenarios

The selected ARIMAX path begins at `$3.25/MMBtu` in August 2026, remains close to `$3.25/MMBtu` around December and January, falls to `$2.62/MMBtu` in May and recovers to `$2.92/MMBtu` in July 2027.

The selected ARIMAX, ARIMAX `(1,1,1)` and seasonal SARIMAX forecasts produce similar central price paths. Their similarity suggests that differencing and the annual seasonal term have little effect on the current central forecast. The EIA path contains a larger winter peak and is retained as an external scenario.

Each statistical forecast is also shown beside a fixed 50/50 midpoint with the EIA path. These combinations are illustrative model risk scenarios rather than forecasts selected through development testing. Only the midpoint between the selected model and EIA is carried into the storage valuation.

## Storage decision model

For each month, a linear programme chooses injection, withdrawal and closing inventory while enforcing:

- minimum and maximum inventory;
- monthly injection and withdrawal limits;
- injection and withdrawal efficiency losses;
- injection, withdrawal and holding costs per unit;
- a fixed monthly contract fee;
- fixed initial and final inventory; and
- discounted monthly cash flows.

The main illustrative assumptions are:

| Assumption | Value |
| --- | ---: |
| Working capacity | 1,000,000 MMBtu |
| Maximum injection | 200,000 MMBtu per month |
| Maximum withdrawal | 200,000 MMBtu per month |
| Initial and final inventory | 0 MMBtu |
| Injection efficiency | 98% |
| Withdrawal efficiency | 98% |
| Injection cost | $0.03/MMBtu |
| Withdrawal cost | $0.03/MMBtu |
| Holding cost | $0.01/MMBtu per month |
| Monthly contract fee | $0 |
| Annual discount rate | 5% |

### July 2026 forecast based values

| Price scenario | Forecast storage NPV |
| --- | ---: |
| Flat last price path | $0 |
| Seasonal SARIMAX | $16,021 |
| Selected ARIMAX | $18,326 |
| ARIMAX `(1,1,1)` + fundamentals | $18,547 |
| Fixed 50/50 ARIMAX and EIA path | $103,946 |
| EIA STEO path | $254,572 |

The assumptions are identical in every row. The large change in value comes from the timing and size of the spreads in each forecast curve, showing the model risk in a deterministic storage exercise.

## Storage decision backtest

For each forecast year from 2017 to 2025, the notebook optimises a schedule using the forecast available at that date, freezes every decision and revalues the unchanged schedule using later realised monthly prices.

| Forecast source | Mean forecast NPV | Median forecast NPV | Mean realised NPV | Median realised NPV | Positive / zero / negative periods |
| --- | ---: | ---: | ---: | ---: | ---: |
| Selected ARIMAX | $67,577 | $44,621 | -$36,414 | -$39,095 | 1 / 1 / 7 |
| EIA STEO | $226,791 | $176,067 | $184,831 | $0 | 3 / 3 / 3 |

The selected model's lower pooled price error does not translate into consistently useful storage timing. EIA is also inconsistent, and its median realised value is zero, but its no action years avoid operating costs when the published curve does not contain enough spread.

Each row is a separate annual decision made and discounted at a different July forecast date. The values are therefore described using their distribution rather than treated as the NPV of one continuous strategy. They are illustrative decision backtests, not verified trading profits.

The notebook also plots the cumulative sum of the annual realised values to show how the separate outcomes develop across forecast years. This is an illustrative running sum rather than a portfolio valuation calculated at one common date.

## Sensitivity analysis

Capacity is tested from 100,000 to 300,000 MMBtu so the range crosses the selected schedule's peak inventory. At the base operating cost, forecast NPV rises from about $9,200 at 100,000 MMBtu to $18,200 at 200,000 MMBtu, with little further gain at 300,000 MMBtu.

At 300,000 MMBtu capacity, increasing the injection and withdrawal charge from $0.01 to $0.05/MMBtu reduces forecast NPV from about $33,900 to $7,700.

## Main findings

- Storage, HDD and CDD forecasts available at the time improve pooled accuracy relative to the tested price only models and benchmarks.
- Explicit seasonal price error terms do not improve the development result; the useful seasonal information enters through the forecast drivers.
- The selected `d = 0` model wins the stated pooled MAE comparison, but `d = 1` models are stronger in several calmer periods and become preferred when 2022 is removed.
- The selected model's prediction intervals are too narrow.
- Lower average forecast error does not guarantee useful storage timing.
- Deterministic storage value is highly sensitive to the chosen forecast curve.

## Validation

Fourteen automated tests check:

- vintage dates, status counts, consecutive months, forecast windows and required values;
- zero activity when flat prices cannot cover costs;
- a known two month storage spread;
- inventory conservation;
- capacity and operating rate limits;
- agreement between discounted cash flows and reported value;
- evaluation of a frozen schedule without optimising again;
- preservation of nonzero opening inventory; and
- invalid or infeasible inputs.

Every retained statistical fit is also checked for numerical convergence. The notebook stops rather than reporting an unfinished fit.

## Tools used

- pandas and NumPy for time series preparation and calculations;
- Matplotlib and Seaborn for visualisation;
- statsmodels for ADF testing and ARIMA family models;
- SciPy for linear storage optimisation;
- openpyxl for the archived workbook extraction and Excel output; and
- Python's `unittest` framework for data and numerical checks.

## Repository contents

```text
.
├── data/
│   ├── README.md
│   ├── eia_steo_july_vintages.csv
│   ├── eia_steo_vintage_manifest.csv
│   └── henry_hub_monthly.csv
├── outputs/
│   └── development_backtest_results.xlsx
├── tests/
│   ├── test_storage_valuation.py
│   └── test_vintage_data.py
├── extract_steo_vintages.py
├── gas_storage_valuation.ipynb
├── storage_valuation.py
├── requirements.txt
└── README.md
```

## Scope and limitations

- Monthly spot price averages are used instead of a traded forward curve, so the valuation is not risk neutral.
- The level model is selected for forecast performance despite the ADF result for the log price level, and its advantage is partly linked to the 2022 forecast year.
- Future storage, HDD and CDD are EIA forecasts; uncertainty in those paths is omitted from the conditional model intervals.
- The EIA price benchmark may contain broader judgement and related assumptions, so it is external rather than fully independent econometric evidence.
- Seven development forecast years cover a limited set of market regimes.
- The first development forecast year has only 54 monthly training observations, limiting confidence in longer seasonal relationships.
- Future weather, supply and geopolitical shocks cannot be inferred from planned storage and weather paths alone.
- The central log price forecast is a conditional median rather than a bias corrected expected price.
- The redesign was informed by the full historical record, so 2024 and 2025 are later evaluations rather than untouched prospective tests.
- Contract inputs are illustrative rather than quoted facility terms.
- Monthly optimisation omits daily deliverability, bid and ask spreads, market impact, liquidity, credit and other operational detail.
