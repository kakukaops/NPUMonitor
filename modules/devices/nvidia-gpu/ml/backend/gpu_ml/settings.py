import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
BINDINGS = json.loads((BASE / 'config/bindings.json').read_text())
METRICS = BINDINGS['metrics']
from nvidia_gpu_ml import plugin  # explicit device extension, including historical models
from gpu_ml_runtime.catalog import TEMPLATES
DATA = Path(os.environ.get('GPU_ML_DATA', '/data'))
PROMETHEUS = os.environ.get('PROMETHEUS_URL', 'http://prometheus:9090').rstrip('/')
NIGHTINGALE = os.environ.get('NIGHTINGALE_URL', 'http://nightingale:17000').rstrip('/')
SIMULATION = os.environ.get('GPU_ML_SIMULATION', 'false').lower() == 'true'
POLL = float(os.environ.get('GPU_ML_POLL_SECONDS', '2'))
FRESHNESS = float(os.environ.get('GPU_ML_FRESHNESS_SECONDS', '15'))
# Registered custom schemas are loaded before model artifacts are opened.
DEFAULT_CLUSTER = os.environ.get('GPU_ML_DEFAULT_CLUSTER', 'existing-prometheus')
MAX_POINTS = 12000
