"""Regression checks for restored pipeline alignment and evaluation boundaries."""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from pipeline.score import score_new_reviews
from pipeline.train import TARGETS, prepare_holdout


class LegacyPipelineTests(unittest.TestCase):
    def training_frame(self):
        return pd.DataFrame({
            "review_text": [f"Distinct review number {i}" for i in range(80)],
            **{target: [i % 2 for i in range(80)] for target in TARGETS},
        })

    def test_holdout_deduplicates_normalized_text_before_split(self):
        frame = self.training_frame()
        duplicate = frame.iloc[[0]].copy()
        duplicate["review_text"] = " DISTINCT   REVIEW NUMBER 0 "
        train, test, metadata = prepare_holdout(pd.concat([frame, duplicate]))
        train_keys = set(train.review_text.str.lower().str.replace(r"\s+", " ", regex=True))
        test_keys = set(test.review_text.str.lower().str.replace(r"\s+", " ", regex=True))
        self.assertFalse(train_keys.intersection(test_keys))
        self.assertEqual(metadata["duplicates_removed"], 1)
        self.assertEqual(metadata["train_records"], 60)
        self.assertEqual(metadata["test_records"], 20)

    def test_holdout_rejects_conflicting_annotations(self):
        frame = self.training_frame()
        duplicate = frame.iloc[[0]].copy()
        duplicate[TARGETS[0]] = 1
        with self.assertRaisesRegex(ValueError, "conflicting labels"):
            prepare_holdout(pd.concat([frame, duplicate]))

    def test_holdout_rejects_single_class_targets(self):
        frame = self.training_frame()
        frame[TARGETS[0]] = 0
        with self.assertRaisesRegex(ValueError, "5 positive and 5 negative"):
            prepare_holdout(frame)

    def test_score_preserves_review_rows_and_category_columns(self):
        frame = pd.DataFrame({
            "review_id": range(7),
            "drug": ["Example"] * 7,
            "review_text": [f"review {i}" for i in range(7)],
            "rating": [3] * 7,
            "created_at": pd.date_range("2025-01-01", periods=7),
        })
        probabilities = np.arange(35, dtype=float).reshape(7, 5) / 35
        model = MagicMock()
        model.predict_proba.return_value = probabilities
        connection = MagicMock()
        connection.execute.return_value.df.return_value = frame
        mlflow = SimpleNamespace(
            set_tracking_uri=MagicMock(),
            sklearn=SimpleNamespace(load_model=MagicMock(return_value=model)),
        )
        duckdb = SimpleNamespace(connect=MagicMock(return_value=connection))
        with patch.dict(sys.modules, {"mlflow": mlflow, "duckdb": duckdb}):
            scores = score_new_reviews("unused.duckdb", "runs:/example/model")
        self.assertEqual(scores.review_id.tolist(), list(range(7)))
        np.testing.assert_array_equal(scores[TARGETS].to_numpy(), probabilities)
        connection.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
