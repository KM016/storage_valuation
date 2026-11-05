"""Small, reproducible checks for the existing July forecasting experiment.

These are diagnostics, NOT an automated model search. The 2024--25 results were
already inspected and are never used to pick specifications or tune parameters.
Run in the repository root: python model_validation.py
"""

import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
import numpy as np
import pandas as pd
from scipy.stats import jarque_bera, t
from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.stattools import adfuller, kpss

from forecasting import (MODEL_SPECS, load_data, point_in_time_history,
                         prepare_features, spread_metrics)

DEV = tuple(range(2017, 2024))
REVIEW = (2024, 2025)  # previously reviewed, excluded from model selection
ORIGINS = (2017, 2020, 2023, 2025)


def unit_root_checks(vintages, years=ORIGINS):
    """ADF null: unit root; KPSS null: level stationarity."""
    records = []
    for year in years:
        log_price = np.log(point_in_time_history(vintages, year).price)
        for name, series in (("log price", log_price),
                             ("first log difference", log_price.diff().dropna())):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # kpss p values are table bounded
                kpss_p = float(kpss(series, regression="c", nlags="auto")[1])
            records.append(dict(year=year, series=name, n=len(series),
                                adf_p=float(adfuller(series, autolag="AIC")[1]),
                                kpss_p=kpss_p))
    return pd.DataFrame(records)


def residual_and_parameter_checks(vintages, years=ORIGINS):
    """Fit each PREEXISTING model, examine residuals and coefficient drift.

    In-sample tests are diagnostics, not proof of out-of-sample performance.
    Twelve initial filtered residuals are omitted to reduce initialization effects.
    """
    residual_rows, parameter_rows = [], []
    for year in years:
        history = point_in_time_history(vintages, year)
        train_x, _ = prepare_features(history, history)
        for name, cfg in MODEL_SPECS.items():
            fields = cfg["features"]
            model = SARIMAX(np.log(history.price), order=cfg["order"],
                            trend=cfg.get("trend", "c"),
                            exog=train_x[fields] if fields else None,
                            enforce_stationarity=True, enforce_invertibility=True)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fitted = model.fit(disp=False, maxiter=400)
                if not fitted.mle_retvals.get("converged", False):
                    fitted = model.fit(method="bfgs", disp=False, maxiter=600)
            ok = bool(fitted.mle_retvals.get("converged", False))
            resid = pd.Series(fitted.resid).iloc[12:].dropna()
            if len(resid) < 20:
                raise ValueError("Insufficient residual observations")
            residual_rows.append(dict(year=year, model=name, n=len(history),
                converged=ok, AIC=float(fitted.aic), BIC=float(fitted.bic),
                Ljung_Box_12_p=float(acorr_ljungbox(resid, lags=[12],
                                                      return_df=True).lb_pvalue.iloc[0]),
                Jarque_Bera_p=float(jarque_bera(resid).pvalue),
                ARCH_LM_6_p=float(het_arch(resid, nlags=6)[1])))
            for coefficient, estimate in fitted.params.items():
                parameter_rows.append(dict(year=year, model=name,
                                           parameter=coefficient, estimate=float(estimate)))
    return pd.DataFrame(residual_rows), pd.DataFrame(parameter_rows)


def paired_interval(differences):
    """Descriptive paired t-interval by annual forecast vintage (not by month)."""
    sample = np.asarray(differences, dtype=float)
    n = len(sample)
    if n < 2 or not np.isfinite(sample).all():
        raise ValueError("At least two finite, paired annual observations are required")
    width = t.ppf(.975, df=n-1) * sample.std(ddof=1) / np.sqrt(n)
    return float(sample.mean()), float(sample.mean() - width), float(sample.mean() + width)


def model_comparison(forecasts, annual):
    """Annual MAE, spread MAE and realised NPV. No winner selected on test years."""
    sample = forecasts[forecasts.year.isin(DEV + REVIEW)].copy()
    sample["abs_error"] = (sample.forecast - sample.actual).abs()
    annual_mae = sample.groupby(["year", "model"]).abs_error.mean().rename("price_MAE")
    spread = spread_metrics(sample).set_index(["year", "model"])["spread_MAE"]
    outcomes = annual.set_index(["year", "model"])["realised_NPV"]
    joined = pd.concat([annual_mae, spread, outcomes], axis=1).reset_index()
    joined["period"] = np.where(joined.year.isin(DEV), "development", "previously_reviewed")
    comparison = joined.groupby(["period", "model"]).agg(
        years=("year", "nunique"), price_MAE=("price_MAE", "mean"),
        spread_MAE=("spread_MAE", "mean"), realised_NPV=("realised_NPV", "mean"),
        positive_years=("realised_NPV", lambda x: int((x > 1e-6).sum())))
    comparison = comparison.reset_index()
    # predefined comparison against eia, not every possible model pair.
    contrasts = []
    pivot = joined[joined.period == "development"].pivot(
        index="year", columns="model", values=["price_MAE", "spread_MAE", "realised_NPV"])
    for name in MODEL_SPECS:
        if ("price_MAE", name) not in pivot.columns:
            continue
        for metric in ("price_MAE", "spread_MAE", "realised_NPV"):
            d = pivot[(metric, name)] - pivot[(metric, "EIA STEO forecast")]
            mean, low, high = paired_interval(d.to_numpy())
            contrasts.append(dict(model=name, metric=metric, years=len(d),
                                  mean_difference_vs_EIA=mean,
                                  CI95_lower=low, CI95_upper=high))
    return joined, comparison, pd.DataFrame(contrasts)



def log_transform_sensitivity(forecasts):
    """Compare conditional lognormal mean against exp(mu) without fitting new models.

    Uses the identical frozen-schedule contract and observed monthly prices.
    The exercise is a sensitivity check, not another selection criterion.
    """
    from economics import CONTRACT, evaluate_curve
    rows = []
    complete = forecasts[forecasts.year.isin(DEV + REVIEW)]
    for (year, model), subset in complete.groupby(["year", "model"]):
        if subset["median"].isna().any():
            continue  # no lognormal transformation for external benchmarks
        subset = subset.sort_values("date")
        actual = pd.Series(subset.actual.to_numpy(dtype=float),
                           index=pd.to_datetime(subset.date))
        for method, values in (("lognormal mean", subset.forecast),
                               ("lognormal median", subset["median"])):
            prices = pd.Series(values.to_numpy(dtype=float), index=actual.index)
            result = evaluate_curve(prices, actual, CONTRACT)
            rows.append(dict(year=year, model=model, transformation=method,
                             realised_NPV=result["realised_npv"],
                             forecast_NPV=result["predicted_npv"]))
    return pd.DataFrame(rows)


def run_validation(save=True):
    root = PROJECT_ROOT
    forecast_file = root / "outputs" / "fixed" / "fixed_forecasts.csv"
    economic_file = root / "outputs" / "fixed" / "fixed_annual_storage.csv"
    if not forecast_file.exists() or not economic_file.exists():
        raise FileNotFoundError("Run the main notebook first to generate saved forecasts and NPV")
    forecasts = pd.read_csv(forecast_file, parse_dates=["date"])
    annual = pd.read_csv(economic_file)
    _, vintages = load_data()
    stationarity = unit_root_checks(vintages)
    residual, parameters = residual_and_parameter_checks(vintages)
    annual_results, comparison, paired = model_comparison(forecasts, annual)
    transforms = log_transform_sensitivity(forecasts)
    if save:
        out = root / "outputs" / "diagnostics"
        for name, frame in (("stationarity_checks", stationarity),
                            ("residual_checks", residual),
                            ("parameter_stability", parameters),
                            ("annual_model_results", annual_results),
                            ("model_comparison", comparison),
                            ("paired_development_contrasts", paired),
                            ("log_transform_sensitivity", transforms)):
            frame.to_csv(out / f"{name}.csv", index=False)
    return stationarity, residual, parameters, annual_results, comparison, paired, transforms


if __name__ == "__main__":
    stationarity, residual, parameters, annual, comparison, paired, transforms = run_validation()
    print("\nStationarity (ADF / KPSS):\n", stationarity.round(3).to_string(index=False))
    print("\nResidual diagnostics:\n", residual.round(4).to_string(index=False))
    print("\nDevelopment comparison:\n", comparison.query("period == 'development'").round(3).to_string(index=False))
    print("\nPaired 95% intervals vs EIA:\n", paired.round(3).to_string(index=False))

    print("\nBack-transform sensitivity:\n", transforms.groupby(["model", "transformation"]).realised_NPV.mean().round().to_string())
