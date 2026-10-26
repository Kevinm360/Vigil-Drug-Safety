"""Compatibility import for the preserved Streamlit model studio."""
from pathlib import Path
import sys

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from backend.serious_outcome import *  # noqa: F401,F403
