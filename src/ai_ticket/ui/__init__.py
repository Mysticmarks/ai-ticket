"""Frontend assets for the AI Ticket dashboard."""

from importlib.resources import files
from pathlib import Path


def get_ui_dist_path() -> Path:
    """Return the path to the built UI distribution assets."""
    return Path(files(__package__) / "dist")


__all__ = ["get_ui_dist_path"]
