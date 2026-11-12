#!/usr/bin/env bash
# Historical entrypoint: implementation has one canonical device-owned location.
set -euo pipefail
repository="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
exec bash "$repository/modules/devices/nvidia-gpu/ml/scripts/anomaly-demo.sh" "$@"
