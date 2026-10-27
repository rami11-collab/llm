"""Explicit mechanical and keyword metrics; none is semantic answer accuracy."""

from statistics import mean, median
import unicodedata


def normalized(value):
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def measure_claims(claims, sources):
    """Independent evaluator of the documented source-ID/contiguous-quote contract."""
    by_id = {str(source.get("id", "")): source for source in sources}
    checks = []
    for claim in claims:
        if not isinstance(claim, dict):
            checks.append({"source_exists": False, "quote_matches": False, "valid": False})
            continue
        source = by_id.get(str(claim.get("source_id", "")))
        quotation = normalized(claim.get("quote", ""))
        quote_matches = bool(source and len(quotation) >= 12
                             and quotation in normalized(source.get("text", "")))
        checks.append({"source_exists": bool(source), "quote_matches": quote_matches,
                       "valid": bool(quote_matches and str(claim.get("text", "")).strip())})
    return {"total": len(checks), "source_valid": sum(c["source_exists"] for c in checks),
            "quote_valid": sum(c["quote_matches"] for c in checks),
            "valid": sum(c["valid"] for c in checks), "checks": checks}


def keyword_measure(answer, groups, answered):
    text = normalized(answer)
    matches = [any(normalized(term) in text for term in group) for group in groups]
    return {"matched_groups": sum(matches) if answered else 0,
            "total_groups": len(groups),
            "complete": bool(answered and groups and all(matches)),
            "group_coverage": ratio(sum(matches), len(groups)) if answered else 0.0}


def score_response(case, mode, response, elapsed, error=None):
    response = response or {}
    sources = response.get("sources", [])
    proposed = measure_claims(response.get("generated_claims", []), sources)
    delivered = measure_claims(response.get("claims", []), sources)
    answer = response.get("answer", "")
    abstained = bool(response.get("abstained")) if not error else False
    answered = bool(str(answer).strip() and not abstained and not error)
    keywords = keyword_measure(answer, case.get("keyword_groups", []), answered)
    expected = set(case.get("expected_source_ids", []))
    returned = {source.get("id") for source in sources}
    trace = response.get("trace", [])
    tools = response.get("tool_results", [])
    plan = response.get("plan", {})
    role = case.get("expected_tool_role")
    external = {"crossref_lookup": "crossref", "arxiv_search": "arxiv"}.get(role)
    audit_ran = mode == "agent" and any(event.get("step") == "evidence_auditor" for event in trace)
    if external:
        attempted = any(result.get("tool") == external for result in tools)
        tool_ok = any(result.get("tool") == external and result.get("ok") for result in tools)
        predicted_ok = plan.get("predicted_action") == external
    elif role == "evidence_audit":
        attempted, tool_ok, predicted_ok = audit_ran, audit_ran, None
    else:
        attempted, tool_ok, predicted_ok = None, None, None
    return {
        "case_id": case["id"], "category": case["category"], "mode": mode,
        "question": case["question"], "error": error, "answered": answered,
        "abstained": abstained, "wall_latency_seconds": elapsed,
        "reported_latency_seconds": response.get("latency_seconds"),
        "generated_claims": proposed["total"], "generated_source_valid": proposed["source_valid"],
        "generated_quote_valid": proposed["quote_valid"], "generated_valid": proposed["valid"],
        "delivered_claims": delivered["total"], "delivered_source_valid": delivered["source_valid"],
        "delivered_quote_valid": delivered["quote_valid"], "delivered_valid": delivered["valid"],
        "citation_applicable": mode != "llm", "keyword_complete_heuristic": keywords["complete"],
        "keyword_group_coverage_heuristic": keywords["group_coverage"],
        "expected_source_ids": sorted(expected), "returned_source_ids": sorted(returned),
        "actual_context_recall": ratio(len(expected & returned), len(expected)),
        "plan_action": plan.get("action"), "predicted_action": plan.get("predicted_action"),
        "plan_origin": plan.get("origin"), "expected_tool_role": role,
        "expected_tool_attempted": attempted, "upstream_tool_ok": tool_ok,
        "llm_predicted_external_route_correct": predicted_ok,
        "tool_cache_statuses": [result.get("cache_status") for result in tools],
        "automatic_auditor_invoked": audit_ran,
        "response": response,
        "independent_generated_checks": proposed["checks"],
        "independent_delivered_checks": delivered["checks"],
    }


def summarize(rows, modes):
    summary = {}
    for mode in modes:
        content = [row for row in rows if row["mode"] == mode and row["category"] != "tool_routing"]
        answerable = [row for row in content if row["category"] == "answerable"]
        unknown = [row for row in content if row["category"] == "unanswerable"]
        generated = sum(row["generated_claims"] for row in content)
        generated_valid = sum(row["generated_valid"] for row in content)
        delivered = sum(row["delivered_claims"] for row in content)
        delivered_valid = sum(row["delivered_valid"] for row in content)
        latency = [row["wall_latency_seconds"] for row in content]
        summary[mode] = {
            "content_cases": len(content), "answerable_cases": len(answerable),
            "unanswerable_cases": len(unknown), "errors": sum(bool(row["error"]) for row in content),
            "answerable_answered": sum(row["answered"] for row in answerable),
            "answerable_coverage": ratio(sum(row["answered"] for row in answerable), len(answerable)),
            "unanswerable_abstained": sum(row["abstained"] for row in unknown),
            "unanswerable_abstention_rate": ratio(sum(row["abstained"] for row in unknown), len(unknown)),
            "unanswerable_answered": sum(row["answered"] for row in unknown),
            "generated_claims": generated, "generated_valid_claims": generated_valid,
            "generated_mechanical_validity": ratio(generated_valid, generated),
            "delivered_claims": delivered, "delivered_valid_claims": delivered_valid,
            "delivered_mechanical_validity": ratio(delivered_valid, delivered),
            "delivered_invalid_claims": delivered - delivered_valid,
            "citation_applicable": mode != "llm",
            "answerable_with_valid_delivered_claim": sum(row["answered"] and row["delivered_valid"] > 0 for row in answerable),
            "answerable_valid_claim_coverage": ratio(sum(row["answered"] and row["delivered_valid"] > 0 for row in answerable), len(answerable)),
            "keyword_complete_count_heuristic": sum(row["keyword_complete_heuristic"] for row in answerable),
            "keyword_complete_rate_heuristic": ratio(sum(row["keyword_complete_heuristic"] for row in answerable), len(answerable)),
            "keyword_group_coverage_mean_heuristic": mean(row["keyword_group_coverage_heuristic"] for row in answerable) if answerable else None,
            "latency_median_seconds": median(latency) if latency else None,
            "latency_mean_seconds": mean(latency) if latency else None,
        }
    external = [row for row in rows if row["category"] == "tool_routing"
                and row["expected_tool_role"] in {"crossref_lookup", "arxiv_search"}]
    audits = [row for row in rows if row["category"] == "tool_routing" and row["expected_tool_role"] == "evidence_audit"]
    return {"variants": summary, "external_tool_routing": {
        "cases": len(external), "expected_tool_attempted": sum(bool(row["expected_tool_attempted"]) for row in external),
        "upstream_success": sum(bool(row["upstream_tool_ok"]) for row in external),
        "llm_predicted_route_correct": sum(bool(row["llm_predicted_external_route_correct"]) for row in external),
        "cache_statuses": [status for row in external for status in row["tool_cache_statuses"]],
    }, "automatic_auditor_cases": {
        "cases": len(audits), "invoked": sum(row["automatic_auditor_invoked"] for row in audits),
        "scope": "Automatic pipeline-node invocation, not an LLM-selected routing decision.",
    }}
