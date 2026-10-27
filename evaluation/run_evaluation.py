"""Run the frozen authored evaluation, preserving every actual model response.

Usage: python -m evaluation.run_evaluation [--resume]
Network access is required for the two local model servers and live tool cases.
"""

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import time
import traceback
import uuid

from evidencedesk.agent import EvidenceAgent
from evidencedesk.config import ROOT, SETTINGS
from evidencedesk.tools import audit_claims
from evaluation.metrics import score_response, summarize

RESULTS = ROOT / "evaluation" / "results"
CASES = ROOT / "evaluation" / "cases.json"
MODES = ("llm", "basic", "agent")


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def write_csv(path, rows, fields=None):
    if not rows:
        return
    fields = fields or list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(row.get(key), ensure_ascii=False)
                             if isinstance(row.get(key), (dict, list)) else row.get(key)
                             for key in fields})


def frozen_metadata():
    backend = {str(path.relative_to(ROOT)): sha256(path)
               for path in sorted((ROOT / "evidencedesk").glob("*.py"))}
    runtime_dir = Path(os.environ.get("EVIDENCEDESK_RUNTIME_DIR", str(ROOT / "runtime"))).expanduser().resolve()
    model_paths = sorted((runtime_dir / "models").glob("*.gguf"))
    if not model_paths:
        raise FileNotFoundError(
            f"No GGUF models found in {runtime_dir / 'models'}. "
            "Run scripts/setup_models.py from the project root, or set EVIDENCEDESK_RUNTIME_DIR."
        )
    models = [{"filename": path.name, "bytes": path.stat().st_size,
               "sha256": sha256(path)}
              for path in model_paths]
    manifest_path = runtime_dir / "manifest.json"
    manifest_origin = "selected_runtime_directory"
    if not manifest_path.exists():
        manifest_path = ROOT / "runtime" / "manifest.json"
        manifest_origin = "project_pinned_manifest"
    manifest_metadata = None
    runtime_release = "b11899"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        actual_models = {model["filename"]: model for model in models}
        assets = []
        for asset in manifest.get("assets", []):
            entry = {key: asset.get(key) for key in (
                "filename", "kind", "repo", "revision", "release", "sha256")
                if asset.get(key) is not None}
            actual = actual_models.get(asset.get("filename"))
            if actual is not None:
                entry["actual_model_matches_declared_bytes_and_sha256"] = (
                    actual["sha256"] == asset.get("sha256")
                    and actual["bytes"] == asset.get("size"))
            if asset.get("kind") == "runtime" and asset.get("release"):
                runtime_release = asset["release"]
            assets.append(entry)
        manifest_metadata = {"path": str(manifest_path.resolve()),
                             "origin": manifest_origin, "sha256": sha256(manifest_path),
                             "assets": assets}
    versions = {}
    for package in ("langgraph", "numpy", "requests", "matplotlib"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return {
        "created_utc": now(), "python": platform.python_version(),
        "platform": platform.platform(), "library_versions": versions,
        "llama_cpp_release": runtime_release, "models": models,
        "runtime_directory": str(runtime_dir), "runtime_manifest": manifest_metadata,
        "settings": {key: str(value) if isinstance(value, Path) else value
                     for key, value in asdict(SETTINGS).items()},
        "inference": {"temperature": 0, "seed": 42,
                      "answer_max_tokens": 420, "planner_max_tokens": 128},
        "backend_sha256": backend,
        "corpus_sha256": sha256(SETTINGS.corpus_path), "cases_sha256": sha256(CASES),
        "mode_order_within_each_content_case": list(MODES),
        "timing_policy": "One sequential request at a time; no automatic retry; setup and model hashing excluded. Local model processes already running; document index and 20 retrieval probes run before timed content requests. Existing external-tool cache allowed and status recorded.",
        "interpretation": [
            "Twenty authored answerable, six unanswerable corpus cases across three end-to-end variants, plus six full-agent tool/auditor cases: 84 actual ask calls.",
            "Full agent may rewrite retrieval queries; basic RAG uses the original question. This is not a pure auditor-only causal ablation.",
            "Mechanical validity means supplied source-ID plus contiguous normalized quote plus nonempty claim. It does not establish semantic entailment or truth.",
            "Closed-book LLM has no source access. Its mechanical citation count is retained transparently but source-validity is not an applicable comparison metric.",
            "Keyword coverage is a predeclared lexical heuristic, not semantic answer accuracy. Human semantic review fields remain blank.",
            "Four external routing attempts and upstream successes are separate from two automatic auditor-node invocations. Audit is not one of the planner's selectable actions.",
            "All questions and labels are separate from the eleven-document indexed corpus; no test questions are indexed.",
            "One deterministic-seed run on one small curated corpus has no confidence interval or broad benchmark/SOTA claim. Cached tool latency is not live upstream latency.",
        ],
    }


def auditor_challenges(documents):
    source = next(document for document in documents if document["id"] == "P08")
    quote = "GRACE addresses two failure modes: responses lacking explicit grounding and fabricated answers when retrieved evidence is insufficient."
    valid = {"text": "GRACE studies grounding and insufficient evidence.", "source_id": "P08", "quote": quote}
    cases = [
        ("C01", "Valid source and contiguous quote", valid, True),
        ("C02", "Unknown source ID", dict(valid, source_id="P99"), False),
        ("C03", "Fabricated quotation", dict(valid, quote="This system guarantees perfect accuracy."), False),
        ("C04", "Noncontiguous quotation", dict(valid, quote="GRACE addresses two failure modes: fabricated answers"), False),
        ("C05", "Quotation below minimum length", dict(valid, quote="GRACE"), False),
        ("C06", "Empty claim text", dict(valid, text=""), False),
        ("C07", "False claim paired with real quote (semantic boundary)", dict(valid, text="GRACE proves every future AI system is perfectly truthful."), True),
    ]
    output = []
    for case_id, description, claim, expected in cases:
        result = audit_claims([claim], [source])
        passed = bool(result["passed"])
        output.append({"case_id": case_id, "description": description, "claim": claim,
                       "expected_mechanical_pass": expected, "actual_mechanical_pass": passed,
                       "test_passed": passed == expected, "audit": result})
    return output


def retrieval_probe(agent, cases):
    rows = []
    for case in cases:
        if case["category"] != "answerable":
            continue
        started = time.perf_counter()
        found = agent.library.search(case["question"], top_k=3)
        expected = set(case["expected_source_ids"])
        top_ids = {source["id"] for source in found}
        accepted_ids = {source["id"] for source in found
                        if source["score"] >= SETTINGS.retrieval_threshold}
        rows.append({"case_id": case["id"], "question": case["question"],
                     "expected_source_ids": sorted(expected),
                     "top_3": [{"id": source["id"], "score": source["score"]} for source in found],
                     "recall_at_3": len(expected & top_ids) / len(expected),
                     "recall_at_3_after_threshold": len(expected & accepted_ids) / len(expected),
                     "latency_seconds": time.perf_counter() - started})
        print(f"retrieval {case['id']}: gold={','.join(sorted(expected))}, top3={','.join(s['id'] for s in found)}", flush=True)
    return rows


def checkpoint(metadata, rows, total, run_id):
    write_json(RESULTS / "raw_results.json", {"metadata": metadata, "rows": rows})
    fields = [key for key in rows[0] if key not in {
        "response", "independent_generated_checks", "independent_delivered_checks"}] if rows else []
    write_csv(RESULTS / "case_results.csv", rows, fields)
    write_json(RESULTS / "progress.json", {"run_id": run_id, "updated_utc": now(),
               "complete": len(rows) == total, "completed_requests": len(rows),
               "total_requests": total, "last_case": rows[-1]["case_id"] if rows else None,
               "last_mode": rows[-1]["mode"] if rows else None})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    assert len([c for c in cases if c["category"] == "answerable"]) == 20
    assert len([c for c in cases if c["category"] == "unanswerable"]) == 6
    assert len([c for c in cases if c["category"] == "tool_routing"]) == 6
    schedule = [(case, mode) for case in cases if case["category"] != "tool_routing" for mode in MODES]
    schedule += [(case, "agent") for case in cases if case["category"] == "tool_routing"]
    assert len(schedule) == 84
    print("Hashing frozen code, corpus, cases, and both actual GGUF models...", flush=True)
    metadata = frozen_metadata()
    rows = []
    run_id = "frozen-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    if args.resume:
        previous = json.loads((RESULTS / "raw_results.json").read_text(encoding="utf-8"))
        old = previous["metadata"]
        for key in ("backend_sha256", "corpus_sha256", "cases_sha256", "models", "inference"):
            if old[key] != metadata[key]:
                raise RuntimeError(f"Cannot resume: frozen {key} changed")
        metadata, rows, run_id = old, previous["rows"], old["run_id"]
    elif (RESULTS / "raw_results.json").exists():
        raise RuntimeError("Existing results preserved. Use --resume or select a new directory in code.")
    metadata["run_id"] = run_id
    write_json(RESULTS / "run_metadata.json", metadata)
    agent = EvidenceAgent()
    health = agent.models.health()
    print(f"Model health: {health}", flush=True)
    if not all(health.values()):
        raise RuntimeError(f"Both model APIs must be healthy: {health}")
    metadata["health_at_start"] = health
    challenges = auditor_challenges(agent.library.documents)
    write_json(RESULTS / "auditor_challenges.json", challenges)
    if not all(row["test_passed"] for row in challenges):
        raise RuntimeError("Independent auditor challenges failed; do not proceed")
    retrieval_path = RESULTS / "retrieval_results.json"
    if args.resume and retrieval_path.exists():
        retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
    else:
        retrieval = retrieval_probe(agent, cases)
        write_json(retrieval_path, retrieval)
        write_csv(RESULTS / "retrieval_results.csv", retrieval)
    completed = {(row["case_id"], row["mode"]) for row in rows}
    checkpoint(metadata, rows, len(schedule), run_id)
    for case, mode in schedule:
        if (case["id"], mode) in completed:
            continue
        session_id = f"{run_id}-{case['id']}-{mode}"
        started = time.perf_counter()
        response, error = None, None
        try:
            response = agent.ask(case["question"], session_id=session_id, mode=mode, use_cache=True)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            print(traceback.format_exc(), flush=True)
        elapsed = time.perf_counter() - started
        row = score_response(case, mode, response, elapsed, error)
        rows.append(row)
        checkpoint(metadata, rows, len(schedule), run_id)
        print(f"[{len(rows):02d}/84] {case['id']} {mode}: {elapsed:.2f}s; answered={row['answered']}; abstained={row['abstained']}; valid delivered={row['delivered_valid']}/{row['delivered_claims']}; error={error}", flush=True)
    metadata["finished_utc"] = now()
    metadata["backend_unchanged_at_finish"] = metadata["backend_sha256"] == {
        str(path.relative_to(ROOT)): sha256(path) for path in sorted((ROOT / "evidencedesk").glob("*.py"))}
    metadata["corpus_unchanged_at_finish"] = metadata["corpus_sha256"] == sha256(SETTINGS.corpus_path)
    metadata["cases_unchanged_at_finish"] = metadata["cases_sha256"] == sha256(CASES)
    summary = summarize(rows, MODES)
    summary["retrieval"] = {"cases": len(retrieval), "k": 3,
        "gold_sources_retrieved_at_3": sum(row["recall_at_3"] for row in retrieval),
        "mean_recall_at_3": sum(row["recall_at_3"] for row in retrieval) / len(retrieval),
        "gold_sources_retrieved_after_threshold": sum(row["recall_at_3_after_threshold"] for row in retrieval),
        "mean_recall_at_3_after_threshold": sum(row["recall_at_3_after_threshold"] for row in retrieval) / len(retrieval)}
    summary["auditor_challenges"] = {"cases": len(challenges), "expected_results_observed": sum(row["test_passed"] for row in challenges),
                                    "semantic_boundary_case": "C07 deliberately passes a false claim paired with a real quote: no semantic truth guarantee."}
    summary["total_ask_requests"] = len(rows)
    summary["metadata"] = metadata
    write_json(RESULTS / "summary.json", summary)
    write_csv(RESULTS / "variant_summary.csv", [{"mode": mode, **values} for mode, values in summary["variants"].items()])
    review_rows = [{"case_id": row["case_id"], "mode": row["mode"], "question": row["question"],
                    "answer": row["response"].get("answer", ""), "semantic_correctness_human_rating": "",
                    "claim_support_human_rating": "", "reviewer_notes": ""}
                   for row in rows if row["category"] != "tool_routing"]
    write_csv(RESULTS / "human_review_blank.csv", review_rows)
    checkpoint(metadata, rows, len(schedule), run_id)
    write_json(RESULTS / "run_metadata.json", metadata)
    from evaluation.plots import create_plots
    create_plots(RESULTS, summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
