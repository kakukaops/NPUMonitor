"""Explicit opt-in simulation profile; excluded from production profile selection."""
import json
from pathlib import Path
from .selected_catalog import extend_selected_catalog
PROFILE=Path(__file__).with_name('master-profile.json')
def definition():return json.loads(PROFILE.read_text())
def extend_catalog(catalog,profile):return extend_selected_catalog(catalog,profile,definition())
