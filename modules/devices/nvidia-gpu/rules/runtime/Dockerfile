FROM python:3.12.9-slim
WORKDIR /opt/rules
RUN pip install --no-cache-dir PyYAML==6.0.2
COPY modules/devices/nvidia-gpu/rules/runtime/src /opt/rules/runtime/src
COPY modules/devices/nvidia-gpu/rules/scripts/build_os_sre.py modules/devices/nvidia-gpu/rules/scripts/os_sre_provenance.py /opt/rules/scripts/
COPY modules/devices/nvidia-gpu/rules/monitoring/os-sre/definition-base.json modules/devices/nvidia-gpu/rules/monitoring/os-sre/provenance.yaml modules/devices/nvidia-gpu/rules/monitoring/os-sre/profile.yaml /opt/rules/monitoring/os-sre/
COPY modules/devices/nvidia-gpu/rules/monitoring/catalog/xid-review.yaml /opt/rules/monitoring/catalog/xid-review.yaml
RUN mkdir /data && chown 1000:1000 /data
ENV PYTHONPATH=/opt/rules/runtime/src PYTHONDONTWRITEBYTECODE=1
USER 1000:1000
EXPOSE 9480
CMD ["python","-m","npumonitor_rules.cli","serve"]
