"""Device-owned configuration, shared by monitoring and its model extension."""
import os
from pathlib import Path
BASE = Path(os.environ.get('NVIDIA_GPU_ML_ROOT', str(Path(__file__).resolve().parents[2]/'ml')))
