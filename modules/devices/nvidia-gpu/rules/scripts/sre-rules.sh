#!/usr/bin/env bash
set -euo pipefail
module_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
repository="$(cd -- "$module_dir/../../../.." && pwd)"
compose=(docker compose -f "$repository/deploy/nvidia-gpu/rules/reference/compose.yaml")
if [[ "${1:-}" == current-* ]]; then
  export NPUMONITOR_RULES_PROJECT=npumonitor-gpu-rules-master
  export NPUMONITOR_RULES_CONFIG_DIR="$repository/.local/gpu-os-sre-master"
  export NPUMONITOR_RULES_NETWORK=gpu-alert-lab_default
  export NPUMONITOR_RULES_PORT=19476
  export NPUMONITOR_N9E_TOKEN_FILE="$repository/.local/n9e-token"
  export NPUMONITOR_NOTIFY_TOKEN_FILE="$repository/.local/gpu-os-sre-master/notify-token"
  current=(docker compose -f "$repository/deploy/nvidia-gpu/rules/production/compose.yaml" -f "$repository/deploy/nvidia-gpu/rules/current/compose.yaml")
  case "$1" in
    current-up)
      python "$module_dir/scripts/sre_current_setup.py"
      "${current[@]}" build sre-runtime gpu-master-source
      if [[ ! -f "$NPUMONITOR_RULES_CONFIG_DIR/initialized" ]]; then
        "${current[@]}" run --rm --no-deps sre-runtime python -m npumonitor_rules.cli init
        "${current[@]}" run --rm --no-deps sre-watchdog python -m npumonitor_rules.cli watchdog-init
        (umask 077; touch "$NPUMONITOR_RULES_CONFIG_DIR/initialized")
      fi
      "${current[@]}" --profile watchdog up -d --wait --wait-timeout 120 sre-runtime sre-watchdog gpu-master-source gpu-master-prometheus
      "${current[@]}" run --rm --no-deps sre-controller python -m npumonitor_rules.cli sync-plan
      "${current[@]}" run --rm --no-deps sre-controller python -m npumonitor_rules.cli sync
      ;;
    current-cli) shift; "${current[@]}" run --rm --no-deps sre-controller python -m npumonitor_rules.cli "$@" ;;
    current-status) "${current[@]}" ps ;;
    current-simulate) shift; python "$module_dir/scripts/sre_simulate.py" "$@" ;;
    *) exit 2 ;;
  esac
  exit
fi
case "${1:-help}" in
  reference-up)
    if [[ -f "$repository/.local/npumonitor-rules-contract/retired.json" ]]; then
      echo '旧独立验收数据已归档；当前系统请使用 current-up，恢复旧快照请先阅读运行文档。' >&2
      exit 2
    fi
    python "$module_dir/scripts/sre_reference_setup.py" prepare
    "${compose[@]}" build sre-runtime sre-source
    "${compose[@]}" up -d --wait --wait-timeout 180 sre-redis sre-nightingale sre-prometheus sre-source sre-receiver
    python "$module_dir/scripts/sre_reference_setup.py" bootstrap
    if [[ ! -f "$repository/.local/npumonitor-rules-contract/initialized" ]]; then
      "${compose[@]}" run --rm --no-deps sre-runtime python -m npumonitor_rules.cli init
      "${compose[@]}" run --rm --no-deps sre-watchdog python -m npumonitor_rules.cli watchdog-init
      touch "$repository/.local/npumonitor-rules-contract/initialized"
    fi
    "${compose[@]}" up -d --no-deps --wait --wait-timeout 120 sre-runtime sre-watchdog
    "${compose[@]}" exec -T sre-runtime python -m npumonitor_rules.cli sync
    ;;
  status) "${compose[@]}" ps ;;
  logs) "${compose[@]}" logs --tail 80 sre-runtime sre-watchdog ;;
  test) "${compose[@]}" run --rm --no-deps -v "$module_dir/runtime/tests:/opt/rules/runtime/tests:ro" -v "$module_dir/runtime/reference:/opt/rules/runtime/reference:ro" -v "$module_dir/runtime/master:/opt/rules/runtime/master:ro" sre-runtime python -m unittest discover -s /opt/rules/runtime/tests -v ;;
  cli) shift; "${compose[@]}" exec -T sre-runtime python -m npumonitor_rules.cli "$@" ;;
  *) echo 'Usage: sre-rules.sh {reference-up|status|logs|test|cli COMMAND...|current-up|current-cli COMMAND...|current-status|current-simulate SCENARIO}' ;;
esac
