"""Simple storage outcome diagnostics around the *unchanged* LP.

Storage transactions are evaluated against monthly observed price averages.
They are counterfactual settlement proxies, not fills achievable at forecast date.
"""

import numpy as np
import pandas as pd
from storage_valuation import optimise_storage_schedule, evaluate_frozen_schedule

CONTRACT = dict(capacity=1_000_000, max_injection=200_000, max_withdrawal=200_000,
                initial_inventory=0, final_inventory=0,
                injection_efficiency=.98, withdrawal_efficiency=.98,
                injection_cost=.03, withdrawal_cost=.03, holding_cost=.01,
                monthly_contract_fee=0, annual_discount_rate=.05)


def evaluate_curve(forecast, actual, contract=CONTRACT):
    schedule, summary = optimise_storage_schedule(forecast, **contract)
    realised, realised_npv = evaluate_frozen_schedule(schedule, actual)
    # forecast and realised charges are identical because quantities are frozen.
    # price error contribution is linear in net volume, including discounting.
    realised["P&L forecast error"] = (realised["Withdrawal"] - realised["Injection"]) * (
        realised["Realised price"] - realised["Forecast price"]) * realised["Discount factor"]
    predicted_npv = float(summary["Forecast contract NPV"])
    gap = realised_npv - predicted_npv
    if not np.isclose(realised["P&L forecast error"].sum(), gap, atol=1e-5):
        raise AssertionError("Storage P&L attribution did not reconcile")
    return dict(predicted_npv=predicted_npv, realised_npv=float(realised_npv),
                attribution=realised, total_injected=float(schedule.Injection.sum()),
                total_withdrawn=float(schedule.Withdrawal.sum()),
                peak_inventory=float(schedule["Closing inventory"].max()))


def storage_backtest(forecasts, years, models, contract=CONTRACT):
    """One frozen yearly storage schedule per model, same constraints throughout."""
    annual, monthly = [], []
    for year in years:
        yr = forecasts[forecasts.year == year]
        if yr.actual.isna().any():
            raise ValueError(f"No complete realised 12-month outcome for {year}")
        a = (yr[yr.model == "EIA STEO forecast"].set_index("date")
             .sort_index().actual.astype(float))
        if len(a) != 12:
            raise ValueError(f"Incorrect realised price coverage for {year}")
        # oracle is an in sample physical upper bound, never an executable policy.
        _, upper = optimise_storage_schedule(a, **contract)
        oracle_npv = float(upper["Forecast contract NPV"])
        for name in models:
            f = yr[yr.model == name].set_index("date").sort_index().forecast.astype(float)
            if not f.index.equals(a.index):
                raise ValueError(f"Missing or reordered forecasts in {year}, {name}")
            out = evaluate_curve(f, a, contract)
            annual.append(dict(year=year, model=name, forecast_NPV=out["predicted_npv"],
                               realised_NPV=out["realised_npv"],
                               oracle_regret=oracle_npv-out["realised_npv"],
                               injected=out["total_injected"],
                               withdrawn=out["total_withdrawn"],
                               peak_inventory=out["peak_inventory"]))
            diag = out["attribution"].reset_index()
            diag["year"] = year
            diag["model"] = name
            monthly.append(diag)
    return pd.DataFrame(annual), pd.concat(monthly, ignore_index=True)


def fixed_blend(rows, model="ARIMAX + fundamentals", weight=.5):
    """One *predeclared* benchmark, not an optimised weight selected on held-out years."""
    if not 0 <= weight <= 1:
        raise ValueError("Blend weight must be between 0 and 1")
    left = rows[rows.model == model].copy().sort_values(["year", "date"])
    right = rows[rows.model == "EIA STEO forecast"].sort_values(["year", "date"])
    if not left[["year", "date"]].reset_index(drop=True).equals(
            right[["year", "date"]].reset_index(drop=True)):
        raise ValueError("Forecasts have different dates")
    left["forecast"] = (weight * left.forecast.to_numpy() +
                        (1-weight) * right.forecast.to_numpy())
    left["model"] = "Fixed 50/50 ARIMAX–EIA"
    left[["lower", "upper", "median", "log_variance"]] = np.nan
    return pd.concat([rows, left], ignore_index=True)


def economic_summary(annual):
    return (annual.groupby("model", sort=False)
            .agg(mean_NPV=("realised_NPV", "mean"), median_NPV=("realised_NPV", "median"),
                 positive_years=("realised_NPV", lambda v: (v > 1e-6).sum()),
                 negative_years=("realised_NPV", lambda v: (v < -1e-6).sum()),
                 mean_oracle_regret=("oracle_regret", "mean"))
            .sort_values("mean_NPV", ascending=False))
