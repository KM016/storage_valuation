import unittest
from pathlib import Path

import pandas as pd


class VintageDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data_path = Path(__file__).parents[1] / "data" / "eia_steo_july_vintages.csv"
        cls.data = pd.read_csv(
            data_path,
            parse_dates=["release_date", "last_historical_month", "date"],
        )

    def test_each_vintage_has_the_expected_months(self):
        counts = self.data.groupby("vintage_year")["date"].size()
        self.assertEqual(len(counts), 10)
        self.assertTrue((counts == 72).all())

    def test_each_vintage_has_unique_consecutive_months(self):
        for vintage_year, vintage in self.data.groupby("vintage_year"):
            dates = pd.DatetimeIndex(vintage["date"].sort_values())
            expected_dates = pd.date_range(
                start=pd.Timestamp(vintage_year - 4, 1, 1),
                periods=72,
                freq="MS",
            )

            self.assertFalse(dates.has_duplicates)
            self.assertTrue(dates.equals(expected_dates))

    def test_each_vintage_has_expected_status_counts(self):
        expected_counts = {"history_or_estimate": 54, "forecast": 18}

        for _, vintage in self.data.groupby("vintage_year"):
            status_counts = vintage["status"].value_counts().to_dict()
            self.assertEqual(status_counts, expected_counts)

    def test_july_release_only_uses_history_through_june(self):
        for vintage_year, vintage in self.data.groupby("vintage_year"):
            historical = vintage[vintage["status"] == "history_or_estimate"]
            forecast = vintage[vintage["status"] == "forecast"]

            self.assertEqual(historical["date"].max(), pd.Timestamp(vintage_year, 6, 1))
            self.assertEqual(forecast["date"].min(), pd.Timestamp(vintage_year, 7, 1))
            self.assertLess(vintage["release_date"].iloc[0], pd.Timestamp(vintage_year, 8, 1))

    def test_august_to_july_forecast_window_is_complete(self):
        for vintage_year, vintage in self.data.groupby("vintage_year"):
            expected_window = pd.date_range(
                f"{vintage_year}-08-01",
                f"{vintage_year + 1}-07-01",
                freq="MS",
            )
            forecast_dates = pd.DatetimeIndex(
                vintage.loc[vintage["status"] == "forecast", "date"]
            )
            self.assertTrue(expected_window.isin(forecast_dates).all())

    def test_required_values_are_complete_and_positive(self):
        required = ["price", "storage", "hdd", "hdd_normal", "cdd", "cdd_normal"]
        self.assertFalse(self.data[required].isna().any().any())
        self.assertTrue((self.data[["price", "storage"]] > 0).all().all())
        self.assertTrue((self.data[["hdd", "hdd_normal", "cdd", "cdd_normal"]] >= 0).all().all())


if __name__ == "__main__":
    unittest.main()
