"""Repository resource locations, independent of a caller module depth."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PREPROCESSING_ROOT = REPO_ROOT / "pipeline" / "preprocessing"
