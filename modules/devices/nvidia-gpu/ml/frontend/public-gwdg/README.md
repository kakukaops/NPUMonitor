# GWDG v2 DCGM demo subset

This directory contains derived DCGM data from the GWDG GPU Node Telemetry
Dataset for Observability-Aware Early Warning, v2.0.0, by Michael Bidollahkhani,
Freja Nordsiek and Julian M. Kunkel. See [the Zenodo record](https://doi.org/10.5281/zenodo.21932615),
[CITATION.cff](CITATION.cff) and [CC BY 4.0](LICENSE).

This subset was filtered to 18 DCGM inputs and 48 cleaned capture intervals on
19 pseudonymized nodes. Values are aligned to the original 10-second UTC grid.
Missing, unobserved and invalid values remain missing. Per-card readings and
node mean, maximum and fraction missing are stored losslessly. The node XID
series records observed nonzero (1), observed zero (0), or unknown (missing).
The index lists original capture bounds, the research node split, and hashes.
Demo models are trained on demand and exclude evaluation nodes during fitting
and calibration. Supervised methods use the known XID labels. The normal
reference methods use only confirmed XID=0 windows for fitting and calibration.

The data files contain only observations, labels, and derived input summaries.

## Viewing and training

From the GPU ML workspace choose 值班 → 单指标趋势 or 多指标关联预警,
then select 公开数据. Choose a node and a capture interval. The single-metric
page runs the selected method when requested. The joint page displays the
selected time's method results and alarm reasons above the metric cards.

The alert lanes show observed nonzero XID, the selected model's decision, and
missing telemetry in that order. XID and model alarms are shaded. The initial
interval contains both an observed XID and all-DCGM missingness at
2025-03-21 07:51:50 UTC. A current endpoint with zero available inputs
reports 当前无有效监测数据.
