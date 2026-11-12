#!/usr/bin/env bash
# Compatibility entry point; implementation belongs to its module.
set -euo pipefail
repository="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$repository/modules/devices/nvidia-gpu/rules/scripts/lab.sh" "$@"
