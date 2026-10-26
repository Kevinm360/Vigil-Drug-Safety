import pandas as pd
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from legacy.pipeline.ingest import ingest_to_csv
from legacy.pipeline.label import distant_supervision
from legacy.pipeline.train import load_training, train_model
from legacy.pipeline.score import score_new_reviews
from legacy.pipeline.signal import compute_signals, persist_to_duckdb

DUCKDB_PATH = "data/legacy/side_effects.duckdb"

def main():
    # This is a synthetic demonstration pipeline, separate from live FAERS.
    Path("data/silver").mkdir(parents=True, exist_ok=True)
    csv_path = ingest_to_csv("data/bronze/reviews.csv", n=2000)
    df = pd.read_csv(csv_path, parse_dates=["created_at"])
    df = distant_supervision(df)
    df.to_parquet("data/silver/labels.parquet", index=False)

    train_df = load_training(DUCKDB_PATH)
    model_uri, micro_f1, macro_f1 = train_model(train_df)
    print(f"Held-out synthetic review evaluation: micro_f1={micro_f1:.3f} macro_f1={macro_f1:.3f}")
    print("Scores measure recovery of keyword labels, not clinical validity.")

    df_scores = score_new_reviews(DUCKDB_PATH, model_uri)
    df_labels = pd.read_parquet("data/silver/labels.parquet")
    df_signals = compute_signals(df_scores)
    persist_to_duckdb(DUCKDB_PATH, df_labels, df_scores, df_signals)
    print("Pipeline complete. Parquet written to data/silver and data/gold.")


if __name__ == "__main__":
    main()
