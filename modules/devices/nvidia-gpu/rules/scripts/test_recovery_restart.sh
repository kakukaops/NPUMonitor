#!/usr/bin/env bash
set -euo pipefail
module_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
project_dir="$(cd -- "$module_dir/../../../.." && pwd)"
compose=(docker compose -f "$project_dir/deploy/nvidia-gpu/lab/compose.yaml")
cleanup() {
  local task_exit=$?
  trap - EXIT
  set +e
  "${compose[@]}" up -d --wait --wait-timeout 90 prometheus recovery-adapter nightingale
  local restore_exit=$?
  bash "$module_dir/scripts/lab.sh" batch1 scenario normal
  local normal_exit=$?
  if ((restore_exit != 0 || normal_exit != 0)); then
    echo 'FAIL: 实验环境自动恢复失败，请运行 lab.sh status 检查' >&2
    task_exit=1
  fi
  exit "$task_exit"
}
trap cleanup EXIT
bash "$module_dir/scripts/lab.sh" recovery restart-prepare
"${compose[@]}" stop prometheus
bash "$module_dir/scripts/lab.sh" recovery restart-upstream-outage
"${compose[@]}" up -d --wait --wait-timeout 60 prometheus
"${compose[@]}" stop recovery-adapter
bash "$module_dir/scripts/lab.sh" recovery restart-outage
"${compose[@]}" up -d --wait --wait-timeout 60 recovery-adapter
"${compose[@]}" restart nightingale
"${compose[@]}" up -d --wait --wait-timeout 90 nightingale
bash "$module_dir/scripts/lab.sh" recovery restart-nightingale-verify
bash "$module_dir/scripts/lab.sh" recovery restart-finish
