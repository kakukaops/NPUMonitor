# Build with repository root as context; private/local data is never copied.
FROM gpu-alert-lab-ml-demo:0.1.0
USER root
WORKDIR /opt/gpu-ml
COPY modules/platform/requirements-api.txt /tmp/requirements-api.txt
RUN pip install --no-cache-dir -r /tmp/requirements-api.txt
COPY modules/devices/nvidia-gpu/ml/backend /opt/gpu-ml/backend
COPY modules/devices/nvidia-gpu/ml/frontend /opt/gpu-ml/frontend
COPY modules/model-services/runtime /opt/gpu-ml/model_runtime
COPY modules/model-services/contracts /opt/gpu-ml/contracts
COPY modules/model-services/adapters /opt/gpu-ml/adapters
COPY modules/devices/nvidia-gpu/adapters /opt/gpu-ml/device-adapters
COPY modules/devices/nvidia-gpu/ml/config /opt/gpu-ml/config
COPY modules/platform/integrations /opt/gpu-ml/integrations
COPY modules/platform/ml-monitoring/backend /opt/gpu-ml/monitoring
RUN mkdir -p /data && chown 65534:65534 /data
ENV PYTHONPATH=/opt/gpu-ml/backend:/opt/gpu-ml/model_runtime:/opt/gpu-ml/contracts:/opt/gpu-ml/adapters:/opt/gpu-ml/device-adapters:/opt/gpu-ml/integrations:/opt/gpu-ml/monitoring PYTHONDONTWRITEBYTECODE=1 NVIDIA_GPU_ML_ROOT=/opt/gpu-ml
USER 65534:65534
EXPOSE 9460
CMD ["python", "-m", "gpu_ml.main"]
