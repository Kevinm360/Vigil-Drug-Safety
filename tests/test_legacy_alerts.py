"""No-network checks for restored alert cohort and threshold behavior."""
import unittest
from unittest.mock import patch

import pandas as pd

from app import alerts


class LegacyAlertTests(unittest.TestCase):
    def scored(self):
        return pd.DataFrame([{
            "reaction": "NAUSEA", "a": 9, "b": 20, "c": 30, "d": 400,
            "prr": 3.1, "chi2": 8.0, "signal": True,
        }])

    def test_window_contains_seven_complete_days(self):
        self.assertEqual(alerts._week_window("2026-10-23"), ("20261016", "20261022"))

    def test_serious_only_uses_same_cohort_for_scoring(self):
        with patch.object(alerts, "reaction_counts_for_drug", return_value={"NAUSEA": 9}) as counts:
            with patch.object(alerts, "score_reactions", return_value=self.scored()) as score:
                result = alerts.compute_alerts_for_drug(
                    "Example", "20261001", "20261007", prr_min=2, chi2_min=4,
                    min_reports=5, top_n_per_drug=15, serious_only=True, z_min=None,
                )
        self.assertEqual(len(result), 1)
        self.assertEqual(counts.call_args.kwargs["search_extra"], " AND serious:1")
        self.assertEqual(score.call_args.kwargs["search_extra"], " AND serious:1")
        self.assertEqual(score.call_args.kwargs["a_counts"], {"NAUSEA": 9})

    def test_configured_burst_threshold_is_applied(self):
        with patch.object(alerts, "reaction_counts_for_drug", return_value={"NAUSEA": 9}):
            with patch.object(alerts, "score_reactions", return_value=self.scored()):
                with patch.object(alerts, "timeseries", return_value=pd.DataFrame()):
                    with patch.object(alerts, "burst_zscores", return_value=pd.DataFrame({"z": [1.0]})):
                        result = alerts.compute_alerts_for_drug(
                            "Example", "20261001", "20261007", prr_min=2, chi2_min=4,
                            min_reports=5, top_n_per_drug=15, z_min=2.0,
                        )
        self.assertTrue(result.empty)


if __name__ == "__main__":
    unittest.main()
