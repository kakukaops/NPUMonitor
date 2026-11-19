#!/usr/bin/env bash
# Compatibility entry point.
set -euo pipefail
repository="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$repository/scripts/experiment.sh" stop "$@"
