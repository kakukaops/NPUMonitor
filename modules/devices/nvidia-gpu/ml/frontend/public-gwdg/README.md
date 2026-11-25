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
and calibration. The strict unlabeled mode uses node groups based on IDs.

The data files contain only observations, labels, and derived input summaries.

## Viewing and training

From the GPU ML workspace choose 值班 → 单指标趋势 or 多指标关联预警,
then select 公开数据. Choose a node and a capture interval. 运行检测 fits
the chosen method on the other nodes' observations, calibrates it on a
separate node group and evaluates the visible interval. The initial interval
contains both an observed XID and all-DCGM missingness at
2025-03-21 07:51:50 UTC.

On other sources, open 节点 XID 检测. Train a candidate from that source,
review a later interval, then activate the candidate. The initial minimum
for reference training and calibration is 120 windows in each segment.
Supervised training and calibration each require two independent usable XID
episodes and at least five sampled positive and five sampled zero windows.
The complete input uses 30 points per window at 10 seconds. When there are no
valid DCGM inputs across the node at the current point, the result is
当前无有效监测数据. Observed XID remains independently visible.
