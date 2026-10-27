"""Supplement frozen-run aggregates without changing any response or test label."""

import json
from statistics import median, mean
from evaluation.run_evaluation import RESULTS, MODES, write_json, write_csv
from evaluation.metrics import ratio


def main():
    payload = json.loads((RESULTS / "raw_results.json").read_text(encoding="utf-8"))
    rows = payload["rows"]
    assert len(rows) == 84, "Only analyze the completed frozen run"
    breakdown = []
    for mode in MODES:
        content = [row for row in rows if row["mode"] == mode and row["category"] != "tool_routing"]
        for stage in ("generated", "delivered"):
            total = sum(row[stage + "_claims"] for row in content)
            source = sum(row[stage + "_source_valid"] for row in content)
            quote = sum(row[stage + "_quote_valid"] for row in content)
            valid = sum(row[stage + "_valid"] for row in content)
            breakdown.append({"mode": mode, "stage": stage, "content_cases": len(content),
                              "source_comparison_applicable": mode != "llm", "all_claims": total,
                              "source_ID_membership_valid": source,
                              "source_ID_membership_rate": ratio(source, total),
                              "contiguous_quote_valid": quote,
                              "contiguous_quote_rate": ratio(quote, total),
                              "all_mechanical_checks_valid": valid,
                              "all_mechanical_checks_rate": ratio(valid, total),
                              "semantic_support_measured": False})
    write_json(RESULTS / "validity_breakdown.json", breakdown)
    write_csv(RESULTS / "validity_breakdown.csv", breakdown)
    tool_rows = [{key: row.get(key) for key in (
        "case_id", "question", "expected_tool_role", "plan_action", "predicted_action",
        "plan_origin", "expected_tool_attempted", "upstream_tool_ok",
        "llm_predicted_external_route_correct", "automatic_auditor_invoked",
        "tool_cache_statuses", "wall_latency_seconds", "error")}
        for row in rows if row["category"] == "tool_routing"]
    write_csv(RESULTS / "tool_routing.csv", tool_rows)
    assert len({(row["case_id"], row["mode"]) for row in rows}) == 84
    full_content = [row for row in rows if row["mode"] == "agent" and row["category"] != "tool_routing"]
    removed = [{"case_id": row["case_id"], "generated": row["generated_claims"],
                "generated_valid": row["generated_valid"], "delivered": row["delivered_claims"],
                "delivered_valid": row["delivered_valid"], "abstained": row["abstained"]}
               for row in full_content if row["generated_claims"] != row["delivered_claims"]]
    write_json(RESULTS / "full_agent_delivery_changes.json", removed)
    latency_rows = []
    for mode in MODES:
        subset = [row for row in rows if row["mode"] == mode and row["category"] != "tool_routing"]
        latencies = [row["wall_latency_seconds"] for row in subset]
        slowest = max(subset, key=lambda row: row["wall_latency_seconds"])
        latency_rows.append({"mode": mode, "cases": len(subset), "median_seconds": median(latencies),
                             "mean_seconds": mean(latencies), "minimum_seconds": min(latencies),
                             "maximum_seconds": max(latencies), "slowest_case": slowest["case_id"],
                             "excluded_observations": 0})
    write_csv(RESULTS / "latency_summary.csv", latency_rows)
    print(json.dumps({"completed_unique_requests": len(rows), "validity_breakdown": breakdown,
                      "tool_cases": tool_rows, "full_agent_delivery_changes": removed}, indent=2))


if __name__ == "__main__":
    main()
