"""EMA's Important Medical Events list for the label flags (rule label-umbrella). The file is
read in faers/medical_events.py, which the release's lists are read by too."""

from ..medical_events import read_ime

__all__ = ["read_ime"]
