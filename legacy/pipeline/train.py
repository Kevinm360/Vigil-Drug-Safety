import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline
from sklearn.metrics import f1_score, classification_report
from sklearn.model_selection import train_test_split

TARGETS = ["gastrointestinal","neurological","dermatological","cardiovascular","psychiatric"]

RANDOM_STATE = 42


def prepare_holdout(df: pd.DataFrame):
    """Keep repeated review text out of both sides of a reproducible holdout."""
    required = ["review_text", *TARGETS]
    missing = [column for column in required if column not in df]
    if missing:
        raise ValueError("Training data is missing columns: " + ", ".join(missing))
    data = df[required].copy()
    data["review_text"] = data["review_text"].fillna("").astype(str).str.strip()
    data = data.loc[data["review_text"].ne("")].copy()
    for target in TARGETS:
        values = pd.to_numeric(data[target], errors="coerce")
        if values.isna().any() or not values.isin([0, 1]).all():
            raise ValueError(f"{target} labels must be binary 0 or 1.")
        data[target] = values.astype(int)
    data["_text_key"] = data["review_text"].str.lower().str.replace(r"\s+", " ", regex=True)
    if (data.groupby("_text_key")[TARGETS].nunique() > 1).any().any():
        raise ValueError("Identical review texts contain conflicting labels; resolve annotations first.")
    before_deduplication = len(data)
    data = data.drop_duplicates("_text_key").drop(columns="_text_key").reset_index(drop=True)
    if len(data) < 40:
        raise ValueError("At least 40 distinct nonempty review texts are required for evaluation.")
    for target in TARGETS:
        counts = data[target].value_counts()
        if min(int(counts.get(0, 0)), int(counts.get(1, 0))) < 5:
            raise ValueError(f"{target} needs at least 5 positive and 5 negative distinct reviews.")

    # Multilabel targets cannot use sklearn's single-label stratification. Search
    # deterministic candidate splits until each target has both classes in both sets.
    for seed in range(RANDOM_STATE, RANDOM_STATE + 50):
        train, test = train_test_split(data, test_size=0.25, random_state=seed)
        if all(train[target].nunique() == 2 and test[target].nunique() == 2 for target in TARGETS):
            break
    else:
        raise ValueError("Unable to retain both classes for every target in the holdout.")
    metadata = {
        "evaluation_method": "25% holdout after normalized exact-text deduplication",
        "random_state": seed,
        "input_records": len(df),
        "distinct_records": len(data),
        "duplicates_removed": before_deduplication - len(data),
        "train_records": len(train),
        "test_records": len(test),
        "model_fit": "training partition only; holdout remains unseen",
        "limitation": "Lexicon-derived labels on synthetic templates measure keyword recovery, not clinical validity.",
    }
    return train, test, metadata

def load_training(ddb_path: str):
    import duckdb as ddb

    con = ddb.connect(ddb_path, read_only=False)
    df = con.execute("""
        select review_id, drug, review_text, rating, created_at,
               gastrointestinal, neurological, dermatological, cardiovascular, psychiatric
        from 'data/silver/labels.parquet'
    """).df()
    con.close()
    return df

def train_model(df: pd.DataFrame, experiment_name: str = "side_effects_demo"):
    import mlflow

    train, test, metadata = prepare_holdout(df)
    X_train, X_test = train["review_text"], test["review_text"]
    Y_train, Y_test = train[TARGETS], test[TARGETS]

    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1,2), min_df=2)),
        ("clf", OneVsRestClassifier(LogisticRegression(max_iter=1000)))
    ])

    mlflow.set_tracking_uri("file:mlruns")
    mlflow.set_experiment(experiment_name)
    with mlflow.start_run() as run:
        pipe.fit(X_train, Y_train)
        preds = pipe.predict(X_test)
        micro_f1 = f1_score(Y_test, preds, average="micro", zero_division=0)
        macro_f1 = f1_score(Y_test, preds, average="macro", zero_division=0)

        mlflow.log_metric("micro_f1", micro_f1)
        mlflow.log_metric("macro_f1", macro_f1)
        mlflow.log_dict(metadata, "evaluation_metadata.json")
        mlflow.log_param("evaluation", "deduplicated_text_holdout")
        mlflow.log_param("train_records", len(train))
        mlflow.log_param("test_records", len(test))

        mlflow.sklearn.log_model(pipe, artifact_path="model")

        report = classification_report(Y_test, preds, target_names=TARGETS, zero_division=0, output_dict=True)
        mlflow.log_dict(report, "classification_report.json")

        model_uri = f"runs:/{run.info.run_id}/model"
        return model_uri, micro_f1, macro_f1
