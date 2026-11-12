#!/usr/bin/env bash
set -euo pipefail
module_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
project_dir="$(cd -- "$module_dir/../../../.." && pwd)"
compose=(docker compose -f "$project_dir/deploy/nvidia-gpu/lab/compose.yaml")
diagnose() {
  "${compose[@]}" ps -a "$@" || true
  "${compose[@]}" logs --tail 60 "$@" || true
}
ensure_running() {
  local service="$1"
  local running
  running="$("${compose[@]}" ps --status running --services "$service")" || return 1
  if [[ "$running" != "$service" ]]; then
    echo "服务 $service 未运行，正在尝试启动并等待健康检查……" >&2
    if ! "${compose[@]}" up -d --wait --wait-timeout 90 "$service"; then
      diagnose "$service"
      return 1
    fi
  fi
}
case "${1:-help}" in
  preflight)
    docker compose version
    "${compose[@]}" config --quiet
    if ! docker info >/dev/null; then
      echo 'BLOCKED: 当前终端无法连接 Docker。请在宿主机确认 Docker 已启动且当前用户有访问权限。' >&2
      exit 1
    fi
    echo 'PASS: Compose 配置和 Docker 连接正常；尚未验证镜像拉取。'
    ;;
  up)
    bash "$0" preflight
    "${compose[@]}" pull
    "${compose[@]}" up -d --wait --wait-timeout 180
    "${compose[@]}" restart prometheus
    "${compose[@]}" up -d --wait --wait-timeout 180
    "${compose[@]}" ps
    ;;
  sim-up)
    # Add stage-2 services without pulling/restarting Nightingale or Redis.
    bash "$0" preflight
    if ! "${compose[@]}" up -d --wait --wait-timeout 90 gpu-simulator notification-receiver prometheus; then
      diagnose gpu-simulator notification-receiver prometheus
      exit 1
    fi
    "${compose[@]}" restart prometheus
    "${compose[@]}" up -d --wait --wait-timeout 90 prometheus
    "${compose[@]}" ps
    ;;
  diagnose) diagnose "${@:2}" ;;
  verify)
    "${compose[@]}" exec -T -e NIGHTINGALE_URL=http://127.0.0.1:17000 -e PROMETHEUS_URL=http://prometheus:9090 nightingale python3 - < "$module_dir/scripts/check_lab.py"
    ;;
  reload-prometheus) "${compose[@]}" restart prometheus ;;
  scenario|state|events|notify-test)
    if [[ "$1" == scenario && $# != 2 ]]; then
      echo 'Usage: bash scripts/lab.sh scenario NAME' >&2
      exit 2
    fi
    ensure_running gpu-simulator
    if [[ "$1" == events || "$1" == notify-test ]]; then
      ensure_running notification-receiver
    fi
    "${compose[@]}" exec -T gpu-simulator python /app/control.py "$@"
    ;;
  check-rules)
    "${compose[@]}" run --rm --no-deps -v "$module_dir/rules:/rules:ro" gpu-simulator python /app/check_catalog.py
    ;;
  suite)
    if [[ ! -s "$project_dir/.local/n9e-token" ]]; then
      echo '缺少 .local/n9e-token' >&2
      exit 1
    fi
    mkdir -p "$project_dir/.local/reports"
    "${compose[@]}" run --rm --no-deps       -v "$project_dir/.local/n9e-token:/run/secrets/n9e-token:ro"       -v "$project_dir/.local/reports:/results"       gpu-simulator python /app/suite.py "${@:2}"
    ;;
  e2e)
    mkdir -p "$project_dir/.local/reports"
    "${compose[@]}" run --rm --no-deps -v "$project_dir/.local/reports:/results" gpu-simulator python /app/e2e.py
    ;;
  repair-invalid)
    "${compose[@]}" run --rm --no-deps       -v "$project_dir/.local/n9e-token:/run/secrets/n9e-token:ro"       -v "$module_dir/rules:/rules:ro"       gpu-simulator python /app/repair_invalid_rule.py
    ;;
  import-rules|rules|alerts)
    if [[ ! -s "$project_dir/.local/n9e-token" ]]; then
      echo '缺少 .local/n9e-token：请保存夜莺测试管理员 API Token，勿通过聊天发送。' >&2
      exit 1
    fi
    action=inspect
    if [[ "$1" == alerts ]]; then action=events; fi
    if [[ "$1" == import-rules ]]; then action=import; fi
    "${compose[@]}" run --rm --no-deps       -v "$project_dir/.local/n9e-token:/run/secrets/n9e-token:ro"       -v "$module_dir/rules:/rules:ro"       gpu-simulator python /app/n9e.py "$action"
    ;;
  comprehensive-init)
    "${compose[@]}" run --rm --no-deps comprehensive-lifecycle python /app/recovery_adapter.py init
    ;;
  comprehensive-up)
    if [[ ! -s "$project_dir/.local/n9e-token" ]]; then
      echo '缺少 .local/n9e-token：先保存本地测试管理员 API Token。' >&2
      exit 1
    fi
    "${compose[@]}" up -d --wait --wait-timeout 90 comprehensive-source comprehensive-lifecycle notification-receiver prometheus
    "${compose[@]}" restart prometheus
    "${compose[@]}" up -d --wait --wait-timeout 90 prometheus
    bash "$0" comprehensive install
    ;;
  comprehensive)
    mkdir -p "$project_dir/.local/reports"
    program=comprehensive_control.py
    if [[ "${2:-}" == suite ]]; then program=comprehensive_suite.py; fi
    args=("${@:2}")
    if [[ "$program" == comprehensive_suite.py ]]; then args=("${@:3}"); fi
    "${compose[@]}" run --rm --no-deps \
      -v "$project_dir/.local/n9e-token:/run/secrets/n9e-token:ro" \
      -v "$module_dir/rules:/rules" \
      -v "$project_dir/.local/reports:/results" \
      gpu-simulator python "/app/$program" "${args[@]}"
    ;;
  recovery-init)
    "${compose[@]}" run --rm --no-deps recovery-adapter python /app/recovery_adapter.py init
    ;;
  recovery)
    mkdir -p "$project_dir/.local/reports"
    "${compose[@]}" run --rm --no-deps \
      -v "$project_dir/.local/n9e-token:/run/secrets/n9e-token:ro" \
      -v "$module_dir/rules:/rules:ro" \
      -v "$project_dir/.local/reports:/results" \
      gpu-simulator python /app/recovery_lab.py "${@:2}"
    ;;
  recovery-probe)
    mkdir -p "$project_dir/.local/reports"
    "${compose[@]}" run --rm --no-deps \
      -v "$project_dir/.local/n9e-token:/run/secrets/n9e-token:ro" \
      -v "$module_dir/rules:/rules:ro" \
      -v "$project_dir/.local/reports:/results" \
      gpu-simulator python /app/recovery_probe.py
    ;;
  batch1)
    if [[ ! -s "$project_dir/.local/n9e-token" ]]; then
      echo '缺少 .local/n9e-token' >&2
      exit 1
    fi
    mkdir -p "$project_dir/.local/reports"
    program=batch1.py
    if [[ "${2:-}" == suite ]]; then program=batch1_suite.py; fi
    args=("${@:2}")
    if [[ "$program" == batch1_suite.py ]]; then args=("${@:3}"); fi
    "${compose[@]}" run --rm --no-deps \
      -v "$project_dir/.local/n9e-token:/run/secrets/n9e-token:ro" \
      -v "$module_dir/rules:/rules:ro" \
      -v "$project_dir/.local/reports:/results" \
      gpu-simulator python "/app/$program" "${args[@]}"
    ;;
  test)
    "${compose[@]}" run --rm --no-deps -v "$module_dir/tests:/tests:ro" gpu-simulator python -m unittest discover -s /tests -v
    ;;
  status) "${compose[@]}" ps -a ;;
  logs) "${compose[@]}" logs --tail 100 "${@:2}" ;;
  down) "${compose[@]}" down ;;
  images) "${compose[@]}" images --format json ;;
  *) echo 'Usage: bash scripts/lab.sh {comprehensive-init|comprehensive-up|comprehensive {install|state|scenario NAME|rules|suite [--case hardware|quality|platform|semantics]}|preflight|up|sim-up|diagnose [service]|verify|reload-prometheus|scenario NAME|state|events|notify-test|check-rules|import-rules|rules|alerts|repair-invalid|e2e|suite|recovery-init|recovery {install|state|suite}|recovery-probe|batch1 {import|rules|state|scenario NAME|suite [--case NAME]}|test|status|logs [service]|down|images}' ;;
esac
