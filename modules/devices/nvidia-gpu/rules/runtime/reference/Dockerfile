FROM python:3.12.9-slim
WORKDIR /fixture
COPY modules/devices/nvidia-gpu/rules/runtime/reference/fixture.py /fixture/fixture.py
COPY modules/devices/nvidia-gpu/rules/runtime/reference/injection.html /fixture/injection.html
RUN mkdir /data && chown 1000:1000 /data
USER 1000:1000
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["python","/fixture/fixture.py"]
