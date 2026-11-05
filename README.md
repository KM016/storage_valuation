# Natural Gas Forecasting and Storage Valuation

A quantitative research project connecting natural gas price forecasts with physical storage decisions, comparing plans set in July against decisions updated each month.

> Personal Project
> Date: 08/2026

## Project overview

This project builds on the forecasting and storage ideas I first encountered during the J.P. Morgan Quantitative Research Job Simulation. The original submissions remain unchanged. This is a separate personal project using a longer price series, archived EIA forecasts and a monthly storage optimisation model.

The research asks three questions:

1. Can storage and weather information available at the time improve Henry Hub price forecasts?
2. Do monthly forecast updates improve price accuracy, predictions of future price differences and storage profitability?
3. How do ARIMAX decisions compare with the EIA's published price forecasts under the same fixed and rolling storage policies?

The project uses **one forecasting and storage framework**. For both ARIMAX and the external EIA benchmark, it compares a storage schedule fixed in July with a schedule updated each month. The same physical constraints, settlement prices and discounting rules apply to all four policies. A price only ARIMA model is included as a forecasting control.

The complete analysis is in [gas_storage_valuation.ipynb](gas_storage_valuation.ipynb). Storage values are based on hypothetical physical operations and monthly spot price settlements, not executable trading profits or prices derived from a traded forward curve.

## Data

The project uses three committed public data snapshots:

- realised monthly [Henry Hub spot prices](https://fred.stlouisfed.org/series/MHHNGSP), originally published by EIA and downloaded through FRED;
- July editions of the [EIA Short Term Energy Outlook](https://www.eia.gov/outlooks/steo/outlook.php) from 2017 to 2026; and
- 108 archived monthly STEO releases, from July 2017 to June 2026, used for monthly decisions.

Each vintage contains the information published at that point in time:

| Variable | EIA series | Use |
| --- | --- | --- |
| Henry Hub price | `NGHHUUS` | Historical or estimated training prices and external EIA forecast benchmark |
| Working gas inventory | `NGWGPUS` | Storage surplus feature |
| Heating degree days | `ZWHDPUS` | Heating demand feature |
| Cooling degree days | `ZWCDPUS` | Cooling demand feature |

The archive also includes the corresponding ten year average HDD and CDD series. The EIA's future Henry Hub price forecast is **not** used as an explanatory variable in ARIMAX. It is retained as an external benchmark.

The notebook runs from the committed CSV files without downloading the original workbooks. The July extraction script is at [scripts/extract_steo_vintages.py](scripts/extract_steo_vintages.py); its source manifest records workbook URLs and checksums. The monthly extracts also have a [source manifest](data/monthly/manifests/rolling_arimax_source_manifest.csv). The 108 original monthly Excel workbooks are not bundled. Full definitions, units, dates and July vintage checksums are in [data/README.md](data/README.md).

## Point in time forecast design

The historical study covers nine August to July storage contracts, beginning in 2017 and ending in 2026. For each contract, the forecast source and decision frequency determine the price information available to the optimiser.

The two decision policies are:

- **Fixed July:** Use the July STEO vintage to forecast the following August through July, optimise all 12 months and execute that schedule without changes.
- **Rolling monthly:** Before each decision from August through July, use the previous month's published STEO vintage, optimise the months still remaining and execute only the current month's action. Inventory carries forward to the next decision.

We apply both policies to **ARIMAX and EIA**, producing four comparable strategies. Rolling ARIMAX refits the statistical model each month. Rolling EIA uses EIA's published price curve from the same monthly release. Neither strategy can use a release published after its decision date.

For ARIMAX, the training series ends before the decision, and storage reference levels and feature scaling are calculated using training data only. Future HDD, CDD and storage values come from the vintage already available at the time. The July price is not treated as observed when generating the July forecast.

The 2017–2023 contracts are used for model development, with 2024 and 2025 reported separately. July 2026 is used for a future contract proposal, not historical scoring.

## Forecasting approach

The statistical models forecast **log Henry Hub prices**. ADF and KPSS tests examine stationarity, while AIC, BIC, Ljung–Box, Jarque–Bera and ARCH diagnostics assess fitted model behaviour. Model comparisons use development data rather than storage profitability.

Three specifications are examined:

- **ARIMA(1,0,0):** a price only control;
- **ARIMA(1,1,1):** a differenced price only alternative; and
- **ARIMAX(1,0,0) + fundamentals:** storage surplus, HDD and CDD, with standardisation based only on training data.

The final statistical evaluation retains **ARIMA(1,0,0)** and **ARIMAX + fundamentals**. The published EIA STEO price curve is an external benchmark, not another fitted ARIMA model. The main storage comparison uses ARIMAX and EIA, each with fixed and rolling decisions.

Because the storage objective uses linear cash flows, log price predictions are converted into conditional expected prices using `exp(mu + variance / 2)`, rather than the median `exp(mu)`. This assumes a Gaussian conditional log price distribution and does not account for errors in EIA's future storage and weather inputs.

## Storage decision model

Each month, a linear programme chooses injection, withdrawal and closing inventory while enforcing:

- storage capacity and monthly flow limits;
- injection and withdrawal efficiency losses;
- transaction, holding and contract costs;
- zero initial and final inventory; and
- discounted monthly cash flows.

The illustrative contract assumptions are:

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

The optimiser uses the forecast price path available at each decision. Fixed policies commit to their July schedules, while rolling policies revise only the remaining months, starting from the inventory already held. Realised NPV is calculated afterward using observed monthly average spot prices, with every cash flow discounted from the original July contract origin.

A no trade policy has zero NPV because this illustrative contract has no fixed fees. Perfect hindsight is an upper bound calculated with future prices already known, not an executable strategy.

## Forecasting results

### Development forecast years: July 2017 to July 2023

| Model | MAE ($/MMBtu) | RMSE ($/MMBtu) |
| --- | ---: | ---: |
| **ARIMAX + fundamentals** | **0.897** | **1.326** |
| ARIMA(1,0,0) | 1.031 | 1.474 |
| EIA STEO forecast | 1.033 | 1.532 |
| ARIMA(1,1,1) | 1.374 | 2.139 |

ARIMAX produces the lowest pooled MAE and RMSE over the seven development contracts. The differenced ARIMA model performs worse than the simpler price only control, so ARIMA(1,0,0) is retained for the main forecasting comparison.

The ARIMAX 95% prediction intervals cover only **77.4%** of development observations. Coverage is about 90.5% over months 1–6, falling to 61.9% for months 7–9 and 66.7% for months 10–12. These conditional intervals underestimate uncertainty, particularly at longer horizons.

### Forecast accuracy across nine historical contracts

The fixed July forecasts provide a common starting point for comparing the selected models:

| Model | Fixed forecast MAE ($/MMBtu) | RMSE ($/MMBtu) | Mean bias ($/MMBtu) |
| --- | ---: | ---: | ---: |
| **ARIMAX + fundamentals** | **0.848** | **1.280** | −0.118 |
| ARIMA(1,0,0) | 0.941 | 1.398 | −0.125 |
| EIA STEO forecast | 0.961 | 1.415 | +0.056 |

To assess monthly updating, we compare each rolling forecast for the current decision month with the original July forecast for that same target month, across **108 contract months**:

| Price forecast policy | Current decision MAE ($/MMBtu) |
| --- | ---: |
| Fixed July ARIMAX | 0.848 |
| **Rolling ARIMAX** | **0.678** |
| Fixed July EIA | 0.961 |
| **Rolling EIA** | **0.642** |

Rolling forecasts use newer information, so this compares decision policies rather than predictions made with identical information or at identical forecast horizons. Forecast errors also vary considerably across contracts, particularly during the large gas price movements around 2021 and 2022.

### Price spread accuracy

Storage decisions depend on predicting **relative prices between future months**, not just each month's price. We therefore calculate spread MAE from pairs of remaining months within the same decision's forecast curve, averaging within each contract and then across all nine contracts.

| Strategy | Mean decision time spread MAE ($/MMBtu) |
| --- | ---: |
| **Fixed ARIMAX** | **0.686** |
| Fixed EIA | 0.697 |
| Rolling ARIMAX | 0.697 |
| Rolling EIA | 0.701 |

Both monthly policies improve current decision price MAE, but neither improves this measure of price spread accuracy. More accurate individual price forecasts do not necessarily produce better storage decisions.

## Storage decision backtest

All four forecast policies use the same storage contract, observed prices, inventory accounting and discount origin. The historical experiment covers nine separate August to July contracts.

| Strategy | Mean realised annual NPV | Median realised annual NPV | Positive contracts |
| --- | ---: | ---: | ---: |
| Fixed ARIMAX | −$61,933 | −$39,095 | 1 / 9 |
| Rolling ARIMAX | +$19,880 | +$34,676 | 6 / 9 |
| Fixed EIA STEO | +$184,831 | $0 | 3 / 9 |
| Rolling EIA STEO | +$120,482 | −$31,473 | 3 / 9 |
| No trade | $0 | $0 | 0 / 9 |
| Perfect hindsight | +$726,067 | +$386,437 | 9 / 9 |

Rolling ARIMAX beats fixed ARIMAX in six of the nine contracts, raising average annual NPV by **$81,813**. However, the paired 95% confidence interval **[−$99,925, +$263,552]** includes zero. The sample is too small to conclude that updating ARIMAX reliably improves storage profitability.

Rolling EIA beats fixed EIA in only three contracts. Its mean annual NPV is **$64,349 lower** than fixed EIA's, and the paired 95% confidence interval **[−$191,321, +$62,623]** also includes zero. Fixed EIA achieves the highest mean annual NPV of the four forecast policies, despite being profitable in only three contracts. Rolling EIA also has a higher mean NPV than rolling ARIMAX.

The notebook presents annual NPVs, the annual comparison chart and cumulative NPV curves. The cumulative curves add the results of separate hypothetical contracts; they do not represent a continuously invested trading account. Perfect hindsight is shown for comparison only.

## July 2026 forecast scenario

The retained ARIMA and ARIMAX models produce forecasts for August 2026 to July 2027 using the July 2026 STEO vintage. EIA's published price forecast is shown alongside them as an external scenario.

ARIMA predicts a relatively stable price path, while ARIMAX and EIA imply more seasonal variation. Under the ARIMAX price curve, the optimiser produces this hypothetical schedule:

- Inject 200,000 MMBtu in October 2026 and withdraw 192,080 MMBtu in December.
- Inject about 8,247 MMBtu in April and 200,000 MMBtu in May 2027, then withdraw 200,000 MMBtu in July.

| Price scenario | Forecast storage NPV |
| --- | ---: |
| ARIMAX + fundamentals | **$23,338** |

The schedule accounts for storage losses and ends with zero inventory. This is a forecast valuation, not realised profit. The August 2026 to July 2027 contract is excluded from all historical performance comparisons.

## Main findings

- ARIMAX with storage and weather fundamentals produces the lowest price error in the fixed forecast comparisons.
- Monthly updating reduces current decision price MAE for both ARIMAX and EIA, but does not improve decision time price spread MAE for either source.
- Rolling ARIMAX raises mean annual hypothetical NPV from −$61,933 to +$19,880 and wins in six of nine contracts, but the paired confidence interval includes zero.
- Rolling EIA produces lower average NPV than fixed EIA, which is the strongest of the four forecast policies by mean annual NPV.
- Better forecast accuracy does not guarantee more profitable storage decisions. The nine contract sample, conditional prediction intervals and simplified storage assumptions do not establish an executable trading edge.

## Limitations

While the results provide useful insights into natural gas forecasting and storage valuation, there are several limitations:

- **Limited sample size:** The analysis covers only nine annual storage contracts. This makes it difficult to establish whether improvements in profitability are statistically reliable. The paired 95% confidence intervals include zero for both rolling comparisons.

- **Forecast uncertainty:** ARIMAX's 95% prediction intervals achieved only 77.4% coverage during the development period, suggesting that the model underestimates uncertainty. These intervals also assume EIA's future weather and storage forecasts are accurate.

- **Simplified storage model:** The linear programme assumes fixed storage capacity, injection and withdrawal limits, and constant operating efficiencies. It excludes transportation, storage rights, inventory dependent flow rates and other practical constraints.

- **Hypothetical profitability:** Realised NPV is calculated using historical monthly average Henry Hub spot prices rather than executable transaction prices. The results do not account for market liquidity, bid ask spreads or actual trade execution costs.

- **Dependence on EIA data:** ARIMAX uses EIA's published weather and storage forecasts as explanatory variables. Its results therefore depend partly on the quality of those forecasts, while EIA's own price forecasts provide an external benchmark rather than a fully independent source of information.

Overall, the results suggest that monthly forecast updates can improve price accuracy, but this does not necessarily translate into more profitable storage decisions. The analysis should be viewed as a modelling and valuation exercise rather than evidence of a deployable trading strategy.
