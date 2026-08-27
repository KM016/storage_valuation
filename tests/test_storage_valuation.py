import unittest

import numpy as np
import pandas as pd

from storage_valuation import evaluate_frozen_schedule, optimise_storage_schedule


class StorageValuationTests(unittest.TestCase):
    def setUp(self):
        self.months = pd.date_range("2026-01-01", periods=4, freq="MS")

    def test_flat_prices_with_costs_produce_no_activity(self):
        prices = pd.Series(3.0, index=self.months)
        schedule, summary = optimise_storage_schedule(
            prices,
            capacity=100,
            max_injection=100,
            max_withdrawal=100,
        )

        self.assertTrue(np.allclose(schedule["Injection"], 0))
        self.assertTrue(np.allclose(schedule["Withdrawal"], 0))
        self.assertAlmostEqual(summary["Forecast operating value"], 0)

    def test_known_two_month_spread(self):
        prices = pd.Series([2.0, 5.0], index=self.months[:2])
        schedule, summary = optimise_storage_schedule(
            prices,
            capacity=100,
            max_injection=100,
            max_withdrawal=100,
            injection_efficiency=1,
            withdrawal_efficiency=1,
            injection_cost=0,
            withdrawal_cost=0,
            holding_cost=0,
            annual_discount_rate=0,
        )

        self.assertAlmostEqual(schedule["Injection"].iloc[0], 100)
        self.assertAlmostEqual(schedule["Withdrawal"].iloc[1], 100)
        self.assertAlmostEqual(summary["Forecast operating value"], 300)

    def test_inventory_balance_and_operating_limits(self):
        prices = pd.Series([2.0, 2.5, 4.0, 5.0], index=self.months)
        schedule, _ = optimise_storage_schedule(
            prices,
            capacity=150,
            max_injection=80,
            max_withdrawal=60,
            injection_efficiency=0.98,
            withdrawal_efficiency=0.97,
        )

        expected_closing = (
            schedule["Opening inventory"]
            + 0.98 * schedule["Injection"]
            - schedule["Withdrawal"] / 0.97
        )
        self.assertTrue(np.allclose(schedule["Closing inventory"], expected_closing))
        self.assertTrue((schedule["Closing inventory"] <= 150 + 1e-7).all())
        self.assertTrue((schedule["Injection"] <= 80 + 1e-7).all())
        self.assertTrue((schedule["Withdrawal"] <= 60 + 1e-7).all())
        self.assertAlmostEqual(schedule["Closing inventory"].iloc[-1], 0)

    def test_discounted_cash_flows_match_summary(self):
        prices = pd.Series([2.0, 2.5, 4.0, 5.0], index=self.months)
        schedule, summary = optimise_storage_schedule(
            prices,
            capacity=100,
            max_injection=100,
            max_withdrawal=100,
            monthly_contract_fee=10,
        )

        self.assertAlmostEqual(
            schedule["Discounted cash flow"].sum(),
            summary["Forecast contract NPV"],
        )
        self.assertAlmostEqual(
            summary["Forecast operating value"] - summary["PV of monthly contract fees"],
            summary["Forecast contract NPV"],
        )

    def test_frozen_schedule_is_not_reoptimised(self):
        forecast_prices = pd.Series([2.0, 5.0], index=self.months[:2])
        realised_prices = pd.Series([4.0, 3.0], index=self.months[:2])
        schedule, _ = optimise_storage_schedule(
            forecast_prices,
            capacity=100,
            max_injection=100,
            max_withdrawal=100,
            injection_efficiency=1,
            withdrawal_efficiency=1,
            injection_cost=0,
            withdrawal_cost=0,
            holding_cost=0,
            annual_discount_rate=0,
        )

        _, realised_npv = evaluate_frozen_schedule(schedule, realised_prices)
        self.assertAlmostEqual(realised_npv, -100)

    def test_unreachable_final_inventory_raises_error(self):
        prices = pd.Series([2.0, 3.0], index=self.months[:2])
        with self.assertRaises(ValueError):
            optimise_storage_schedule(
                prices,
                capacity=100,
                max_injection=10,
                max_withdrawal=10,
                final_inventory=100,
            )

    def test_opening_inventory_is_preserved_by_default(self):
        prices = pd.Series([2.0, 3.0], index=self.months[:2])
        schedule, summary = optimise_storage_schedule(
            prices,
            capacity=100,
            max_injection=100,
            max_withdrawal=100,
            initial_inventory=40,
        )

        self.assertAlmostEqual(schedule["Closing inventory"].iloc[-1], 40)
        self.assertGreaterEqual(summary["Peak inventory"], 40)

    def test_invalid_price_curve_raises_error(self):
        prices = pd.Series([2.0, np.nan], index=self.months[:2])
        with self.assertRaises(ValueError):
            optimise_storage_schedule(
                prices,
                capacity=100,
                max_injection=100,
                max_withdrawal=100,
            )

        valid_prices = pd.Series([2.0, 3.0], index=self.months[:2])
        with self.assertRaises(ValueError):
            optimise_storage_schedule(
                valid_prices,
                capacity=np.nan,
                max_injection=100,
                max_withdrawal=100,
            )


if __name__ == "__main__":
    unittest.main()
