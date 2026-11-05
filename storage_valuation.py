"""Simple monthly natural gas storage valuation."""

import numpy as np
import pandas as pd
from scipy.optimize import linprog


def _check_prices(prices):
    """Check that the price curve is a complete monthly pandas Series."""
    # check that prices are stored in the expected format
    if not isinstance(prices, pd.Series):
        raise TypeError("prices must be a pandas Series")
    if prices.empty:
        raise ValueError("prices cannot be empty")
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise TypeError("prices must use a DatetimeIndex")
    if not prices.index.is_monotonic_increasing or prices.index.has_duplicates:
        raise ValueError("price dates must be ordered and unique")

    # check that every month appears exactly once with no gaps
    expected_index = pd.date_range(prices.index[0], periods=len(prices), freq="MS")
    if not prices.index.equals(expected_index):
        raise ValueError("prices must contain consecutive month-start dates")

    # check that all prices are valid positive numbers
    price_values = prices.to_numpy(dtype=float)
    if not np.isfinite(price_values).all() or (price_values <= 0).any():
        raise ValueError("prices must be finite and positive")


def _check_contract_inputs(
    number_of_months,
    capacity,
    max_injection,
    max_withdrawal,
    initial_inventory,
    final_inventory,
    injection_efficiency,
    withdrawal_efficiency,
    injection_cost,
    withdrawal_cost,
    holding_cost,
    monthly_contract_fee,
    annual_discount_rate,
):
    """Check that the contract assumptions can produce a valid schedule."""
    # collect all numeric contract assumptions for validation
    contract_inputs = np.asarray(
        [
            capacity,
            max_injection,
            max_withdrawal,
            initial_inventory,
            final_inventory,
            injection_efficiency,
            withdrawal_efficiency,
            injection_cost,
            withdrawal_cost,
            holding_cost,
            monthly_contract_fee,
            annual_discount_rate,
        ],
        dtype=float,
    )
    # check that every contract assumption is a valid number
    if not np.isfinite(contract_inputs).all():
        raise ValueError("contract inputs must be finite")

    # check the physical storage assumptions
    if capacity <= 0:
        raise ValueError("capacity must be positive")
    if max_injection < 0 or max_withdrawal < 0:
        raise ValueError("injection and withdrawal limits cannot be negative")
    if not 0 < injection_efficiency <= 1:
        raise ValueError("injection_efficiency must lie between zero and one")
    if not 0 < withdrawal_efficiency <= 1:
        raise ValueError("withdrawal_efficiency must lie between zero and one")

    # check that costs and discounting assumptions are valid
    if min(injection_cost, withdrawal_cost, holding_cost, monthly_contract_fee) < 0:
        raise ValueError("costs and fees cannot be negative")
    if annual_discount_rate <= -1:
        raise ValueError("annual_discount_rate must be greater than -1")

    # check that the starting and ending inventories fit inside the facility
    if not 0 <= initial_inventory <= capacity:
        raise ValueError("initial_inventory must lie within storage capacity")
    if not 0 <= final_inventory <= capacity:
        raise ValueError("final_inventory must lie within storage capacity")

    # check that the requested final inventory can physically be reached
    maximum_inventory_increase = number_of_months * max_injection * injection_efficiency
    maximum_inventory_decrease = number_of_months * max_withdrawal / withdrawal_efficiency
    if final_inventory - initial_inventory > maximum_inventory_increase + 1e-9:
        raise ValueError("the final inventory cannot be reached with the injection limit")
    if initial_inventory - final_inventory > maximum_inventory_decrease + 1e-9:
        raise ValueError("the final inventory cannot be reached with the withdrawal limit")


def optimise_storage_schedule(
    prices,
    capacity,
    max_injection,
    max_withdrawal,
    initial_inventory=0.0,
    final_inventory=None,
    injection_efficiency=0.98,
    withdrawal_efficiency=0.98,
    injection_cost=0.03,
    withdrawal_cost=0.03,
    holding_cost=0.01,
    monthly_contract_fee=0.0,
    annual_discount_rate=0.05,
):
    """Find the highest-value monthly schedule for one forecast price curve."""
    # check the forecast prices before running the optimisation
    _check_prices(prices)
    number_of_months = len(prices)

    # finish with the same inventory level unless another target is supplied
    if final_inventory is None:
        final_inventory = initial_inventory

    # check that the contract assumptions are valid
    _check_contract_inputs(
        number_of_months,
        capacity,
        max_injection,
        max_withdrawal,
        initial_inventory,
        final_inventory,
        injection_efficiency,
        withdrawal_efficiency,
        injection_cost,
        withdrawal_cost,
        holding_cost,
        monthly_contract_fee,
        annual_discount_rate,
    )

    # convert prices to an array and discount each months cash flow
    price_values = prices.to_numpy(dtype=float)
    month_numbers = np.arange(1, number_of_months + 1)
    discount_factors = (1 + annual_discount_rate) ** (-month_numbers / 12)

    # build the objective function for injection, withdrawal and inventory
    # linprog minimises, so sales revenue enters with a negative sign
    objective = np.concatenate(
        [
            discount_factors * (price_values + injection_cost),
            -discount_factors * (price_values - withdrawal_cost),
            discount_factors * holding_cost,
        ]
    )

    # create the monthly inventory balance equations
    inventory_constraints = np.zeros((number_of_months, 3 * number_of_months))
    inventory_targets = np.zeros(number_of_months)

    # link each months opening inventory, activity and closing inventory
    for month in range(number_of_months):
        inventory_constraints[month, month] = -injection_efficiency
        inventory_constraints[month, number_of_months + month] = 1 / withdrawal_efficiency
        inventory_constraints[month, 2 * number_of_months + month] = 1

        # the first month starts from the supplied initial inventory
        if month == 0:
            inventory_targets[month] = initial_inventory
        # later months begin with the previous months closing inventory
        else:
            inventory_constraints[month, 2 * number_of_months + month - 1] = -1

    # set the allowed range for injections, withdrawals and inventory
    bounds = (
        [(0, max_injection)] * number_of_months
        + [(0, max_withdrawal)] * number_of_months
        + [(0, capacity)] * (number_of_months - 1)
        + [(final_inventory, final_inventory)]
    )

    # find the storage schedule with the highest discounted value
    solution = linprog(
        objective,
        A_eq=inventory_constraints,
        b_eq=inventory_targets,
        bounds=bounds,
        method="highs",
    )
    # stop if the optimiser cannot find a valid solution
    if not solution.success:
        raise RuntimeError(f"storage optimisation failed: {solution.message}")

    # extract the optimal injection, withdrawal and inventory decisions
    injection = solution.x[:number_of_months]
    withdrawal = solution.x[number_of_months : 2 * number_of_months]
    closing_inventory = solution.x[2 * number_of_months :]

    # remove tiny numerical solver values so the schedule is easier to read
    injection[np.abs(injection) < 1e-7] = 0
    withdrawal[np.abs(withdrawal) < 1e-7] = 0
    closing_inventory[np.abs(closing_inventory) < 1e-7] = 0
    # calculate the opening inventory for each month
    opening_inventory = np.concatenate(([initial_inventory], closing_inventory[:-1]))

    # calculate the individual revenue and cost components
    purchase_cost = price_values * injection
    sales_revenue = price_values * withdrawal
    injection_charge = injection_cost * injection
    withdrawal_charge = withdrawal_cost * withdrawal
    storage_charge = holding_cost * closing_inventory
    contract_fee = np.full(number_of_months, monthly_contract_fee)

    # calculate monthly operating and net cash flows
    operating_cash_flow = (
        sales_revenue
        - purchase_cost
        - injection_charge
        - withdrawal_charge
        - storage_charge
    )
    net_cash_flow = operating_cash_flow - contract_fee

    # store the full optimal monthly schedule in a dataframe
    schedule = pd.DataFrame(
        {
            "Forecast price": price_values,
            "Opening inventory": opening_inventory,
            "Injection": injection,
            "Withdrawal": withdrawal,
            "Closing inventory": closing_inventory,
            "Purchase cost": purchase_cost,
            "Sales revenue": sales_revenue,
            "Injection cost": injection_charge,
            "Withdrawal cost": withdrawal_charge,
            "Holding cost": storage_charge,
            "Contract fee": contract_fee,
            "Discount factor": discount_factors,
            "Operating cash flow": operating_cash_flow,
            "Net cash flow": net_cash_flow,
            "Discounted cash flow": net_cash_flow * discount_factors,
        },
        index=prices.index,
    )
    schedule.index.name = "Month"

    # calculate the overall value of the optimal storage strategy
    operating_value = np.sum(operating_cash_flow * discount_factors)
    contract_fee_value = np.sum(contract_fee * discount_factors)
    contract_npv = operating_value - contract_fee_value
    # count months where injection and withdrawal occur at the same time
    simultaneous_months = int(((injection > 1e-7) & (withdrawal > 1e-7)).sum())

    # calculate the maximum inventory used by the strategy
    peak_inventory = max(initial_inventory, closing_inventory.max())
    # summarise the main valuation and storage results
    summary = pd.Series(
        {
            "Forecast operating value": operating_value,
            "PV of monthly contract fees": contract_fee_value,
            "Forecast contract NPV": contract_npv,
            "Break-even upfront fee": contract_npv,
            "Total injected": injection.sum(),
            "Total withdrawn": withdrawal.sum(),
            "Peak inventory": peak_inventory,
            "Capacity utilisation": peak_inventory / capacity,
            "Simultaneous operating months": simultaneous_months,
        },
        name="Value",
    )

    return schedule, summary


def evaluate_frozen_schedule(schedule, realised_prices):
    """Evaluate an existing schedule without changing its decisions."""
    # check that the realised price curve is valid
    _check_prices(realised_prices)
    # the realised prices must cover exactly the same months as the schedule
    if not schedule.index.equals(realised_prices.index):
        raise ValueError("realised prices must cover the same months as the schedule")

    # copy the original schedule so its decisions remain unchanged
    result = schedule.copy()
    # replace forecast prices with the prices that actually occurred
    result["Realised price"] = realised_prices.to_numpy(dtype=float)
    # recalculate purchase costs and sales revenue using realised prices
    result["Realised purchase cost"] = result["Realised price"] * result["Injection"]
    result["Realised sales revenue"] = result["Realised price"] * result["Withdrawal"]

    # recalculate cash flow while keeping the original storage decisions fixed
    result["Realised net cash flow"] = (
        result["Realised sales revenue"]
        - result["Realised purchase cost"]
        - result["Injection cost"]
        - result["Withdrawal cost"]
        - result["Holding cost"]
        - result["Contract fee"]
    )
    # discount the realised monthly cash flows
    result["Realised discounted cash flow"] = (
        result["Realised net cash flow"] * result["Discount factor"]
    )

    # add the realised discounted cash flows to get the final realised npv
    realised_npv = result["Realised discounted cash flow"].sum()
    return result, realised_npv
