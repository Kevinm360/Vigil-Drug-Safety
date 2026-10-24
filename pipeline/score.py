import pandas as pd

TARGETS = ["gastrointestinal","neurological","dermatological","cardiovascular","psychiatric"]

def score_new_reviews(ddb_path: str, model_uri: str):
    import mlflow
    import duckdb as ddb

    mlflow.set_tracking_uri("file:mlruns")
    model = mlflow.sklearn.load_model(model_uri)

    con = ddb.connect(ddb_path, read_only=False)
    df = con.execute("""
        select review_id, drug, review_text, rating, created_at
        from 'data/silver/labels.parquet'
    """).df()

    proba = model.predict_proba(df["review_text"])
    # OneVsRestClassifier returns one column per target, not one row per target.
    probs = pd.DataFrame(proba, columns=TARGETS, index=df.index)
    out = pd.concat([df[["review_id","drug","created_at"]], probs], axis=1)
    con.close()
    return out
