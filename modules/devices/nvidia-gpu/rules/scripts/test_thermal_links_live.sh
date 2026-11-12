#!/usr/bin/env bash
set -euo pipefail
module_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
project_dir="$(cd -- "$module_dir/../../../.." && pwd)"
compose=(docker compose -f "$project_dir/deploy/nvidia-gpu/review/compose.yaml")
cleanup() {
  local result=$?
  trap - EXIT
  "${compose[@]}" down --volumes || result=1
  exit "$result"
}
trap cleanup EXIT
mkdir -p "$project_dir/.local/reports"
"${compose[@]}" up -d --wait --wait-timeout 60
"${compose[@]}" run --rm --no-deps \
  -v "$project_dir/.local/reports:/results" \
  review-simulator python /app/thermal_links_live.py
