"""Explicit NVIDIA extension; loading this never imports the monitoring engine."""
import json
from .plugin_config import BASE
from gpu_ml_runtime.catalog import TEMPLATES, LEGACY_TYPES, LEGACY_BUILDERS
TEMPLATES.update(json.loads((BASE/'config/bindings.json').read_text())['templates'])
from . import dcgm_scenarios
from .legacy_models import GPUModel, build_model
if GPUModel not in LEGACY_TYPES:
    LEGACY_TYPES.append(GPUModel)
    LEGACY_BUILDERS.append(build_model)
