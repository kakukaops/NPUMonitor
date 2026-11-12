FROM gpu-alert-lab-ml-demo:0.1.0
USER root
WORKDIR /opt/gpu-ml
COPY modules/platform/requirements-api.txt /tmp/requirements-api.txt
RUN pip install --no-cache-dir -r /tmp/requirements-api.txt
# Compatibility lookup only: no monitor engine, store, source, API or Nightingale.
COPY modules/devices/nvidia-gpu/ml/backend/gpu_ml/__init__.py modules/devices/nvidia-gpu/ml/backend/gpu_ml/models.py modules/devices/nvidia-gpu/ml/backend/gpu_ml/pipeline.py modules/devices/nvidia-gpu/ml/backend/gpu_ml/detectors.py modules/devices/nvidia-gpu/ml/backend/gpu_ml/dcgm_scenarios.py /opt/gpu-ml/backend/gpu_ml/
COPY modules/model-services/reference-platform/gpu_ml_platform /opt/gpu-ml/model_platform/gpu_ml_platform
COPY modules/model-services/runtime /opt/gpu-ml/model_runtime
COPY modules/model-services/contracts /opt/gpu-ml/contracts
COPY modules/model-services/adapters /opt/gpu-ml/adapters
COPY modules/devices/nvidia-gpu/adapters /opt/gpu-ml/device-adapters
COPY modules/devices/nvidia-gpu/ml/config /opt/gpu-ml/config
RUN mkdir -p /platform-data && chown 65534:65534 /platform-data
ENV PYTHONPATH=/opt/gpu-ml/backend:/opt/gpu-ml/model_runtime:/opt/gpu-ml/contracts:/opt/gpu-ml/adapters:/opt/gpu-ml/device-adapters:/opt/gpu-ml/integrations:/opt/gpu-ml/monitoring:/opt/gpu-ml/model_platform PYTHONDONTWRITEBYTECODE=1 NVIDIA_GPU_ML_ROOT=/opt/gpu-ml
USER 65534:65534
EXPOSE 9470
CMD ["python", "-m", "gpu_ml_platform.main"]
