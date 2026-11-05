"""Point-in-time July natural-gas forecasts.

One July STEO vintage per origin; no future realised prices enter forecasting.
All model specifications are fixed before the 2024--2025 review period.
"""

from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tools.sm_exceptions import ConvergenceWarning

DATA = Path(__file__).resolve().parent / "data"
FEATURES = ["storage_surplus", "hdd", "cdd", "hdd_deviation", "cdd_deviation"]
REQUIRED = ["price", "storage", "hdd", "hdd_normal", "cdd", "cdd_normal"]

# deliberately small set: simple price only control and two original arimax variants.
# the historical winning model is retained; no new complex search is introduced.
MODEL_SPECS = {
    "ARIMA(1,0,0)": {"order": (1, 0, 0), "features": []},
    "ARIMA(1,1,1)": {"order": (1, 1, 1), "features": [], "trend": "n"},
    "ARIMAX + fundamentals": {"order": (1, 0, 0), "features": ["storage_surplus", "hdd", "cdd"]},
}
BASELINES = ("Last price", "Seasonal naive", "EIA STEO forecast")


def load_data():
    prices = (pd.read_csv(DATA / "henry_hub_monthly.csv", parse_dates=["observation_date"])
              .rename(columns={"observation_date": "Date", "MHHNGSP": "Price"})
              .set_index("Date").sort_index().asfreq("MS"))
    vintages = pd.read_csv(DATA / "eia_steo_july_vintages.csv",
                           parse_dates=["release_date", "last_historical_month", "date"])
    if prices["Price"].isna().any() or (prices["Price"] <= 0).any():
        raise ValueError("Observed Henry Hub prices must be complete and positive")
    if vintages.duplicated(["vintage_year", "date"]).any():
        raise ValueError("Duplicate STEO forecast vintage/month")
    if vintages[REQUIRED].isna().any().any():
        raise ValueError("STEO vintages have missing model inputs")
    return prices, vintages


def point_in_time_history(vintages, year):
    """Historical/estimated EIA rows available by the July release of ``year``."""
    usable = vintages.loc[(vintages["vintage_year"] <= year) &
                          (vintages["status"] == "history_or_estimate")].copy()
    if usable.empty:
        raise ValueError(f"No historical vintage for {year}")
    if not (usable["release_date"] < pd.Timestamp(f"{year}-08-01")).all():
        raise ValueError("An unreleased historical vintage would be used")
    hist = (usable.sort_values(["date", "release_date", "vintage_year"])
            .drop_duplicates("date", keep="last").set_index("date")
            .sort_index().asfreq("MS"))
    if hist.index[-1] != pd.Timestamp(year, 6, 1) or hist[REQUIRED].isna().any().any():
        raise ValueError("Training history is not complete through June")
    return hist


def prepare_features(training, future):
    """Seasonal storage surplus and weather deviations, scaled on training only."""
    monthly_mean_storage = training.groupby(training.index.month)["storage"].mean()
    result = []
    for raw in (training, future):
        frame = pd.DataFrame(index=raw.index)
        expected = raw.index.month.map(monthly_mean_storage).to_numpy(dtype=float)
        frame["storage_surplus"] = (raw["storage"].to_numpy() - expected) / expected
        frame["hdd"] = raw["hdd"]
        frame["cdd"] = raw["cdd"]
        frame["hdd_deviation"] = raw["hdd"] - raw["hdd_normal"]
        frame["cdd_deviation"] = raw["cdd"] - raw["cdd_normal"]
        result.append(frame)
    train_x, future_x = result
    mu = train_x[FEATURES].mean()
    sd = train_x[FEATURES].std(ddof=0).replace(0, 1)
    return (train_x[FEATURES] - mu) / sd, (future_x[FEATURES] - mu) / sd


def seasonal_naive(training_prices, horizon):
    seen = training_prices.to_dict()
    result = {}
    for date in horizon:
        result[date] = seen[date - pd.DateOffset(years=1)]
        seen[date] = result[date]
    return pd.Series(result, dtype=float)


def forecast_year(year, prices, vintages, model_specs=MODEL_SPECS):
    """Forecast Aug--Jul from the July vintage; store a conditional mean on price scale.

    The lognormal correction exp(mu + var/2) is suitable for *expected* linear
    storage cash flows IF the conditional normal log-price model is adequate.
    Conditional 95% bands ignore future STEO-driver forecast uncertainty.
    """
    selected = vintages[vintages.vintage_year == year]
    if selected.empty or selected.release_date.nunique() != 1:
        raise ValueError(f"Missing or ambiguous July vintage for {year}")
    if not (selected.release_date.iloc[0] < pd.Timestamp(year, 8, 1)):
        raise ValueError("July vintage was released after decision cut-off")
    vintage = selected.set_index("date").sort_index()
    history = point_in_time_history(vintages, year)
    horizon = pd.date_range(pd.Timestamp(year, 7, 1), periods=13, freq="MS")
    evaluated = horizon[1:]
    future = vintage.reindex(horizon)
    if future[REQUIRED].isna().any().any() or (future["status"] != "forecast").any():
        raise ValueError("The selected vintage has incomplete future drivers")
    training_x, future_x = prepare_features(history, future)
    actual = prices["Price"].reindex(evaluated)
    # results are intentionally blank for 2026 onward until every month has settled.
    forecasts = {
        "Last price": pd.Series(history.price.iloc[-1], index=horizon),
        "Seasonal naive": seasonal_naive(history.price, horizon),
        "EIA STEO forecast": future.price,
    }
    rows = []
    for name, curve in forecasts.items():
        for date in evaluated:
            rows.append(dict(year=year, date=date, model=name, actual=actual.loc[date],
                             forecast=float(curve.loc[date]), lower=np.nan, upper=np.nan,
                             median=np.nan, log_variance=np.nan, converged=True))
    for name, config in model_specs.items():
        fields = config["features"]
        m = SARIMAX(np.log(history.price), order=config["order"], trend=config.get("trend", "c"),
                    exog=training_x[fields] if fields else None,
                    enforce_stationarity=True, enforce_invertibility=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            fit = m.fit(disp=False, maxiter=400)
        if not fit.mle_retvals.get("converged", False):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ConvergenceWarning)
                fit = m.fit(method="bfgs", disp=False, maxiter=600)
        if not fit.mle_retvals.get("converged", False):
            raise RuntimeError(f"Nonconverged fit: {name}, vintage {year}")
        pred = fit.get_forecast(steps=len(horizon), exog=future_x[fields] if fields else None)
        mu = pd.Series(pred.predicted_mean.to_numpy(), index=horizon)
        var = pd.Series(np.asarray(pred.var_pred_mean), index=horizon)
        if not np.isfinite(var).all() or (var < -1e-10).any():
            raise ValueError("Invalid forecast variance")
        var = var.clip(lower=0)
        # this is e[price] under a conditional lognormal approximation; exp(mu)
        # would be the *median*. we retain both for clear comparability.
        mean_price = np.exp(mu + .5 * var)
        median_price = np.exp(mu)
        ci = pred.conf_int(alpha=.05)
        lo = pd.Series(np.exp(ci.iloc[:, 0].to_numpy()), index=horizon)
        hi = pd.Series(np.exp(ci.iloc[:, 1].to_numpy()), index=horizon)
        for date in evaluated:
            rows.append(dict(year=year, date=date, model=name, actual=actual.loc[date],
                             forecast=float(mean_price.loc[date]),
                             lower=float(lo.loc[date]), upper=float(hi.loc[date]),
                             median=float(median_price.loc[date]),
                             log_variance=float(var.loc[date]), converged=True))
    return pd.DataFrame(rows)


def run_years(years, prices, vintages, model_specs=MODEL_SPECS):
    return pd.concat([forecast_year(y, prices, vintages, model_specs) for y in years],
                     ignore_index=True)


def forecast_metrics(rows):
    """Forecast errors (months are dependent; do not use them as independent CIs)."""
    valid = rows.dropna(subset=["actual"])
    output = []
    for model, sub in valid.groupby("model", sort=False):
        err = sub.forecast - sub.actual
        bands = sub.dropna(subset=["lower", "upper"])
        output.append(dict(model=model, MAE=err.abs().mean(), RMSE=np.sqrt((err**2).mean()),
                           bias=err.mean(), coverage=(
                               ((bands.actual >= bands.lower) & (bands.actual <= bands.upper)).mean()
                               if len(bands) else np.nan)))
    return pd.DataFrame(output).sort_values("MAE").reset_index(drop=True)


def spread_metrics(rows):
    """Per-vintage all-pairs calendar-spread accuracy, with NO claim of independent pairs."""
    out = []
    for (year, model), group in rows.dropna(subset=["actual"]).groupby(["year", "model"]):
        group = group.sort_values("date")
        if len(group) != 12:
            continue
        forecasts = group.forecast.to_numpy()
        actuals = group.actual.to_numpy()
        ii, jj = np.triu_indices(len(group), k=1)
        fd = forecasts[jj] - forecasts[ii]
        ad = actuals[jj] - actuals[ii]
        out.append(dict(year=year, model=model, spread_MAE=np.abs(fd-ad).mean(),
                        direction_accuracy=(np.sign(fd) == np.sign(ad)).mean(),
                        # shares index/forecast date: annual vintage observations only.
                        n_pairs=len(ii)))
    return pd.DataFrame(out)
