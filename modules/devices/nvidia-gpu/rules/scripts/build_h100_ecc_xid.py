#!/usr/bin/env python3
"""Build review-only queries and deterministic promtool fixtures for H100 ECC/XID."""
import argparse
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1] / "monitoring"
TARGET = 'cluster_id="fixture-cluster",job="dcgm",instance="fixture-node:9400"'
DEVICES = 'UUID=~"GPU-FIXTURE-000[01]"'
KEY = "cluster_id,UUID"
COUNTER_LIMIT = 9223372036854775792
XID = "DCGM_FI_DEV_XID_ERRORS"
DOMAINS = {"total": "TOTAL", "device_memory": "DEV", "sram": "SRM"}


def fresh(selector):
    age = f"(time() - timestamp({selector}))"
    return f"({selector} and ({age} >= 0) and ({age} <= 90))"


def guarded(field):
    raw = f"{field}{{{TARGET},{DEVICES}}}"
    current = fresh(raw)
    healthy = fresh(f"up{{{TARGET}}}")
    return raw, (
        f"({current} and on ({KEY}) (count by ({KEY}) ({current}) == 1)"
        f" and on (cluster_id,job,instance) ({healthy} == 1)"
        f" and ({raw} >= 0) and ({raw} < {COUNTER_LIMIT}) and ({raw} == floor({raw})))"
    )


def counter_query(field, recent):
    raw, valid = guarded(field)
    if not recent:
        return f"({valid} > 0)"
    window = f"{raw}[5m]"
    return (
        f"(increase({window}) and {valid}"
        f" and (count_over_time({window}) >= 2)"
        f" and (min_over_time({window}) >= 0)"
        f" and (max_over_time({window}) < {COUNTER_LIMIT})"
        f" and (sum_over_time({window}) >= 0))"
    )


def build():
    xid_review = yaml.safe_load((ROOT / "catalog/xid-review.yaml").read_text())
    records = []
    cases = []

    def add_query(query_id, field, expression, kind):
        records.append({"query_id": query_id, "input": field, "kind": kind,
                        "expression": expression, "default_policy": "disabled"})

    def add_case(name, query_id, field, values, expected=None, up="1+0x12", duplicate=False):
        selector = f'{field}{{{TARGET},UUID="GPU-FIXTURE-0000"}}'
        series = [{"series": f"up{{{TARGET}}}", "values": up}]
        if values is not None:
            series.append({"series": selector, "values": values})
        if duplicate:
            series.append({"series": selector[:-1] + ',replica="other"}', "values": values})
        expression = next(row["expression"] for row in records if row["query_id"] == query_id)
        assertions = [] if expected is None else [
            {"labels": '{cluster_id="fixture-cluster",UUID="GPU-FIXTURE-0000"}', "value": expected}
        ]
        cases.append({"name": f"{query_id}.{name}", "interval": "30s", "input_series": series,
                      "promql_expr_test": [{"expr": f"max by ({KEY}) ({expression})",
                                            "eval_time": "300s", "exp_samples": assertions}]})

    for domain, suffix in DOMAINS.items():
        definitions = [("dbe_history", f"DCGM_FI_DEV_ECC_DBE_AGG_{suffix}", False),
                       ("sbe_trend", f"DCGM_FI_DEV_ECC_SBE_VOL_{suffix}", True)]
        if domain != "total":
            definitions.append(("dbe_detail", f"DCGM_FI_DEV_ECC_DBE_VOL_{suffix}", True))
        for view, field, recent in definitions:
            query_id = f"ecc.{view}.{domain}"
            add_query(query_id, field, counter_query(field, recent), "dashboard")
            add_case("history_without_growth", query_id, field, "7+0x10", 0 if recent else 7)
            add_case("missing", query_id, field, None)
            add_case("stale", query_id, field, "7 _ _ _ _ _ _ _ _ _ _")
            add_case("invalid", query_id, field, "NaN+0x10")
            add_case("duplicate", query_id, field, "7+0x10", duplicate=True)
            if recent:
                add_case("increment", query_id, field, "0+1x10", 10)
                add_case("reset_only", query_id, field, "7 7 7 7 7 0 0 0 0 0 0", 0)
                add_case("invalid_inside_window", query_id, field, "0 1 NaN 1 1 1 1 1 1 1 1")
            else:
                add_case("zero", query_id, field, "0+0x10")
                add_case("sentinel", query_id, field, f"{COUNTER_LIMIT}+0x10")

    raw, valid = guarded(XID)
    def matches(codes):
        return "(" + " or ".join(f"({raw} == {code})" for code in codes) + ")"

    for category, example in [("node_incident_review", 79), ("gpu_reset_review", 64)]:
        codes = [i["code"] for i in xid_review["items"] if i["disposition"] == category]
        query_id = f"xid.{category}"
        add_query(query_id, XID, f"({matches(codes)} and {valid})", "triage_view")
        for code in codes:
            add_case(f"code_{code}", query_id, XID, f"{code}+0x10", code)
        add_case("informational_154", query_id, XID, "154+0x10")
        add_case("contained_94", query_id, XID, "94+0x10")
        add_case("uncontained_95_needs_context", query_id, XID, "95+0x10")
        add_case("zero", query_id, XID, "0+0x10")
        add_case("unknown_code", query_id, XID, "999+0x10")
        add_case("source_down", query_id, XID, f"{example}+0x10", up="0+0x12")
        add_case("duplicate", query_id, XID, f"{example}+0x10", duplicate=True)
        add_case("stale", query_id, XID, f"{example} _ _ _ _ _ _ _ _ _ _")
    return {
        "catalog/ecc-xid-review-queries.yaml": {
            "schema_version": "0.1.0", "scope": "synthetic_review_only",
            "production_admitted": False, "queries": records,
        },
        "tests/ecc-xid-review.promtool.yaml": {
            "rule_files": [], "evaluation_interval": "30s", "tests": cases,
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, data in build().items():
        output = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120)
        path = ROOT / name
        if args.check:
            if path.read_text() != output:
                raise SystemExit(f"生成文件需更新: {path}")
        else:
            path.write_text(output)
    print("PASS: ECC/XID 草案查询与测试样本一致")


if __name__ == "__main__":
    main()
