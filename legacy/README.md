# Preserved research tools

The active React app is in `frontend/`; its API and seriousness models are in `backend/`.
This folder keeps the original Streamlit interface, synthetic review pipeline,
Prefect flow, and weekly alert job available alongside the current app.

Run these commands from the repository root:

```powershell
# Original interface
python -m pip install -r config/requirements/legacy.txt
python -m streamlit run legacy/app/streamlit_app.py

# Synthetic review pipeline (writes data/ outputs)
python -m pip install -r config/requirements/pipeline.txt
python -m legacy.run_pipeline

# Prefect version of that pipeline
python -m legacy.flows.side_effects_flow
```

`app/serious_outcome.py` imports the active model implementation from
`backend/serious_outcome.py`. `jobs/weekly_alerts.py` retains the existing alert
workflow. The preserved database is now `data/legacy/side_effects.duckdb`.
`original_sources/` is an unchanged snapshot of the supplied source files.
See [restoration details](../docs/RESTORATION.md) for the functionality map.
