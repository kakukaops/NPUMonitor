#!/usr/bin/env bash
set -euo pipefail
module_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
root="$(cd -- "$module_dir/../../../.." && pwd)"
compose=(docker compose -f "$root/deploy/nvidia-gpu/lab/compose.yaml")
case "${1:-help}" in
  up)
    "${compose[@]}" config --quiet
    "${compose[@]}" build ml-anomaly-demo
    "${compose[@]}" up -d --no-deps --wait --wait-timeout 90 ml-anomaly-demo
    # Validate before a graceful reload. SIGHUP preserves the existing TSDB and jobs.
    "${compose[@]}" exec -T prometheus promtool check config /etc/prometheus/prometheus.yml
    "${compose[@]}" kill -s SIGHUP prometheus
    "${compose[@]}" exec -T ml-anomaly-demo python -c 'import urllib.request,time; deadline=time.time()+40
while time.time()<deadline:
 try:
  urllib.request.urlopen("http://127.0.0.1:9450/ready",timeout=3); break
 except Exception: time.sleep(2)
else: raise SystemExit("Prometheus 数据未就绪，请查看 demo 日志")'
    echo '异常检测 Demo: http://localhost:19450 （首次采集约需 10 秒）'
    ;;
  test)
    "${compose[@]}" exec -T ml-anomaly-demo python -m unittest discover -s /app -p 'test_*.py' -v
    ;;
  verify)
    "${compose[@]}" exec -T ml-anomaly-demo python /app/verify.py
    ;;
  logs) "${compose[@]}" logs --tail 80 ml-anomaly-demo ;;
  stop) "${compose[@]}" stop ml-anomaly-demo ;;
  *) echo 'Usage: bash scripts/anomaly-demo.sh {up|test|verify|logs|stop}' ;;
esac
