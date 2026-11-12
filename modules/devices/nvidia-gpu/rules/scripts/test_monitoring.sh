#!/usr/bin/env bash
set -euo pipefail
module_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
project_dir="$(cd -- "$module_dir/../../../.." && pwd)"
docker compose -f "$project_dir/deploy/nvidia-gpu/lab/compose.yaml" run --rm --no-deps \
  --entrypoint /bin/promtool -v "$module_dir/monitoring:/work:ro" \
  prometheus test rules /work/tests/ecc_dbe.promtool.yaml /work/tests/h100_batch1.promtool.yaml /work/tests/hardware-lifecycle.promtool.yaml /work/tests/ecc-xid-review.promtool.yaml /work/tests/thermal-links-review.promtool.yaml /work/tests/h100-training.promtool.yaml
