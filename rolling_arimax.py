"""monthly arimax forecasts and rolling storage decisions."""

import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tools.sm_exceptions import ConvergenceWarning

from forecasting import prepare_features
from economics import CONTRACT

FEATURES = ["storage_surplus", "hdd", "cdd"]
REQUIRED = ["price", "storage", "hdd", "hdd_normal", "cdd", "cdd_normal"]


def fit_arimax(training: pd.DataFrame, future: pd.DataFrame) -> pd.DataFrame:
    training_x, future_x = prepare_features(training, future)
    model = SARIMAX(
        np.log(training.price),
        order=(1, 0, 0),
        trend="c",
        exog=training_x[FEATURES],
        enforce_stationarity=True,
        enforce_invertibility=True,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        fitted = model.fit(disp=False, maxiter=400)
    if not fitted.mle_retvals.get("converged", False):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            fitted = model.fit(method="bfgs", disp=False, maxiter=600)
    if not fitted.mle_retvals.get("converged", False):
        raise RuntimeError("Rolling ARIMAX fit did not converge")
    prediction = fitted.get_forecast(steps=len(future), exog=future_x[FEATURES])
    mu = pd.Series(prediction.predicted_mean.to_numpy(), index=future.index)
    variance = pd.Series(np.asarray(prediction.var_pred_mean), index=future.index).clip(lower=0)
    if not np.isfinite(variance).all():
        raise ValueError("Nonfinite ARIMAX forecast variance")
    interval = prediction.conf_int(alpha=0.05)
    return pd.DataFrame(
        {
            "forecast": np.exp(mu + 0.5 * variance),
            "median": np.exp(mu),
            "lower": np.exp(interval.iloc[:, 0].to_numpy()),
            "upper": np.exp(interval.iloc[:, 1].to_numpy()),
            "log_variance": variance,
        },
        index=future.index,
    )

def current_vintage_history(base_history: pd.DataFrame, vintage: pd.DataFrame) -> pd.DataFrame:
    update = vintage[vintage.status == "history_or_estimate"].set_index("date").sort_index()
    combined = pd.concat([base_history, update])
    combined = combined[~combined.index.duplicated(keep="last")].sort_index().asfreq("MS")
    if combined[REQUIRED].isna().any().any():
        raise ValueError("Rolling history became incomplete")
    return combined

def remaining_future(vintage: pd.DataFrame, decision_month: pd.Timestamp, contract_end: pd.Timestamp) -> pd.DataFrame:
    indexed = vintage.set_index("date").sort_index()
    last_history = pd.Timestamp(indexed.last_historical_month.iloc[0])
    lead_in_start = last_history + pd.DateOffset(months=1)
    future = indexed.reindex(pd.date_range(lead_in_start, contract_end, freq="MS"))
    if future.empty or future[REQUIRED].isna().any().any() or (future.status != "forecast").any():
        raise ValueError("Incomplete future ARIMAX input horizon")
    targets = pd.date_range(decision_month, contract_end, freq="MS")
    if not targets.isin(future.index).all():
        raise ValueError("Forecast does not cover the exact remaining contract")
    return future

def rolling_execute(
    year: int,
    decision_forecasts: dict[pd.Timestamp, pd.Series],
    actual: pd.Series,
    optimise_storage_schedule,
    strategy: str = "Rolling ARIMAX",
) -> tuple[pd.DataFrame, float]:
    inventory = 0.0
    records = []
    contract_months = pd.date_range(f"{year}-08-01", periods=12, freq="MS")
    for month_number, decision in enumerate(contract_months, start=1):
        curve = decision_forecasts[decision]
        expected_index = pd.date_range(decision, contract_months[-1], freq="MS")
        if not curve.index.equals(expected_index):
            raise ValueError(f"Rolling curve does not cover remaining contract at {decision.date()}")
        contract = {**CONTRACT, "initial_inventory": inventory, "final_inventory": 0.0}
        schedule, summary = optimise_storage_schedule(curve, **contract)
        action = schedule.iloc[0]
        opening = inventory
        injection = float(action["Injection"])
        withdrawal = float(action["Withdrawal"])
        inventory = float(action["Closing inventory"])
        discount = (1 + CONTRACT["annual_discount_rate"]) ** (-month_number / 12)
        realised_price = float(actual.loc[decision])
        cash = (
            realised_price * (withdrawal - injection)
            - CONTRACT["injection_cost"] * injection
            - CONTRACT["withdrawal_cost"] * withdrawal
            - CONTRACT["holding_cost"] * inventory
            - CONTRACT["monthly_contract_fee"]
        )
        records.append(
            {
                "contract_year": year,
                "strategy": strategy,
                "strategy_type": "ex_ante_policy",
                "month": decision,
                "month_number": month_number,
                "opening_inventory": opening,
                "injection": injection,
                "withdrawal": withdrawal,
                "closing_inventory": inventory,
                "forecast_price": float(curve.iloc[0]),
                "realised_price": realised_price,
                "realised_net_cash_flow": cash,
                "discount_factor": discount,
                "realised_discounted_cash_flow": cash * discount,
                "replan_forecast_npv_from_decision": float(summary["Forecast contract NPV"]),
            }
        )
    trades = pd.DataFrame(records)
    return trades, float(trades.realised_discounted_cash_flow.sum())
