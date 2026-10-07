"""Locations of checked-in artifacts, independent of package nesting."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = REPO_ROOT / 'artifacts'
RESULTS = ARTIFACTS / 'results'
FIGURES = ARTIFACTS / 'figures'
