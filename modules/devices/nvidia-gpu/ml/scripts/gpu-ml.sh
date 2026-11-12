#!/usr/bin/env bash
set -euo pipefail
module_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
repository="$(cd -- "$module_dir/../../../.." && pwd)"
compose=(docker compose -f "$repository/deploy/nvidia-gpu/ml/compose.yaml")
prepare() {
  mkdir -p "$repository/.local"
  python3 - "$repository/.local" <<'PY'
from pathlib import Path
import secrets,sys
root=Path(sys.argv[1])
for role in ('admin','operator','viewer'):
 p=root/('gpu-ml-'+role+'-token')
 if not p.exists():
  p.write_text(secrets.token_urlsafe(32)+'\n')
  # Host parent is private; this read-only file is readable by the non-root container.
  p.chmod(0o644)
platform_token=root/'gpu-ml-model-platform-token'
if not platform_token.exists():platform_token.write_text(secrets.token_urlsafe(32)+'\n');platform_token.chmod(0o644)
p=root/'gpu-ml-n9e-token'
source=root/'n9e-token'
auth=root/'gpu-ml-prometheus-auth.json'
if not auth.exists():auth.write_text('{}\n');auth.chmod(0o644)
guard=root/'gpu-ml-initialized'
if not guard.exists():
 guard.write_text('pending\n');guard.chmod(0o644)
p.write_text(source.read_text() if source.exists() else '')
p.chmod(0o644)
PY
}
case "${1:-help}" in
  up|simulation-up)
    if [[ "$1" == simulation-up && "${GPU_ML_PROMETHEUS_URL:-http://prometheus:9090}" != http://prometheus:9090 ]]; then
      echo '模拟profile仅用于已有隔离实验Prometheus，不混用外部源' >&2; exit 1
    fi
    prepare
    if ! docker image inspect gpu-alert-lab-ml-demo:0.1.0 >/dev/null 2>&1; then
      docker build -t gpu-alert-lab-ml-demo:0.1.0 "$module_dir/demo"
    fi
    services=(gpu-ml)
    if [[ "${GPU_ML_MODEL_PLATFORM_URL:-http://model-platform:9470}" == http://model-platform:9470 ]]; then services+=(model-platform); fi
    "${compose[@]}" build "${services[@]}"
    if [[ "$1" == simulation-up ]]; then
      GPU_ML_SIMULATION=true "${compose[@]}" up -d --no-deps --wait --wait-timeout 180 "${services[@]}"
      printf 'initialized\n' > "$repository/.local/gpu-ml-initialized"
      # Only the known isolated laboratory config is changed, never a configured production URL.
      python3 - "$repository/deploy/nvidia-gpu/lab/prometheus/prometheus.yml" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]);s=p.read_text()
if 'job_name: gpu-ml-simulation' not in s:
 s+='''\n  # Explicit GPU ML simulation profile; original jobs remain unchanged.
  - job_name: gpu-ml-simulation
    scrape_interval: 2s
    metrics_path: /simulation/metrics
    static_configs:
      - targets: ['gpu-ml:9460']
'''
 p.write_text(s)
PY
      docker compose -f "$repository/deploy/nvidia-gpu/lab/compose.yaml" exec -T prometheus promtool check config /etc/prometheus/prometheus.yml
      docker compose -f "$repository/deploy/nvidia-gpu/lab/compose.yaml" kill -s SIGHUP prometheus
    else
      GPU_ML_SIMULATION=false "${compose[@]}" up -d --no-deps --wait --wait-timeout 180 "${services[@]}"
    fi
    printf 'initialized\n' > "$repository/.local/gpu-ml-initialized"
    echo 'GPU ML: http://localhost:19460'
    echo 'Demo页面选择登录角色即可进入；生产关闭GPU_ML_DEMO_LOGIN。'
    ;;
  platform-up)
    prepare
    "${compose[@]}" build model-platform
    "${compose[@]}" up -d --no-deps --wait model-platform
    ;;
  platform-logs) "${compose[@]}" logs --tail 100 model-platform ;;
  platform-backup)
    "${compose[@]}" exec -T model-platform python -m gpu_ml_platform.cli backup
    ;;
  credentials)
    for role in admin operator viewer; do
      path="$repository/.local/gpu-ml-$role-token"
      [[ -f "$path" ]] || { echo '尚未初始化，请先启动服务' >&2; exit 1; }
      printf '%s: ' "$role"; cat "$path"
    done
    ;;
  status) "${compose[@]}" ps ;;
  logs) "${compose[@]}" logs --tail 100 gpu-ml ;;
  stop) "${compose[@]}" stop gpu-ml ;;
  sync|verify)
    program=sync
    [[ "$1" == verify ]] && program=verify
    "${compose[@]}" exec -T gpu-ml python -m gpu_ml.cli "$program"
    ;;
  test)
    "${compose[@]}" run --rm --no-deps -v "$module_dir/tests:/tests:ro" gpu-ml python -m unittest discover -s /tests -v
    "${compose[@]}" run --rm --no-deps -v "$repository/modules/model-services/reference-platform/tests:/platform-tests:ro" model-platform python -m unittest discover -s /platform-tests -v
    ;;
  backup) "${compose[@]}" exec -T gpu-ml python -m gpu_ml.cli backup ;;
  *) echo 'Usage: gpu-ml.sh {up|simulation-up|platform-up|platform-logs|platform-backup|credentials|status|logs|stop|sync|test|verify|backup}' ;;
esac
