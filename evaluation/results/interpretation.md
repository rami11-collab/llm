# Frozen authored-case evaluation

Run `frozen-20261026T131857Z-ca74af` completed all 84 unique `ask` calls with zero thrown request errors. Backend, corpus, and case SHA-256 values were unchanged at completion. Twenty answerable and six missing-evidence questions were each run in three modes, then six tool/auditor cases were run in full-agent mode. The eleven-document corpus contains original attributed research notes, not full papers. Each request used a new session. No results were silently retried or excluded.

| Metric | Closed-book LLM | Basic RAG | Full agent |
|---|---:|---:|---:|
| Answerable questions answered | 19/20 | 19/20 | 13/20 |
| Missing-evidence questions abstained | 2/6 | 0/6 | 5/6 |
| Generated claims mechanically valid | N/A: no sources | 26/26 | 15/16 |
| Delivered claims mechanically valid | N/A: no sources | 25/25 | 14/14 |
| All predeclared keyword groups found | 2/20 | 8/20 | 6/20 |
| Median content latency, seconds | 1.283 | 4.468 | 3.494 |
| Mean content latency, seconds | 1.432 | 4.418 | 14.440 |

The full agent abstained more often when evidence was missing, with lower answerable coverage. Basic RAG also achieved perfect mechanical delivered-claim validity on this run, so the experiment does not demonstrate an aggregate validity advantage over basic RAG. Within the full agent, one generated claim had an invalid quotation (A07) and was removed. Another generated claim had a valid quotation but the draft marked abstention (A15), so it was not delivered. The remaining delivered claims pass source-membership/quote checks, which does not establish answer relevance, entailment, or truth.

Examples reveal this boundary: A01 returned `P01 [P01]`; A10 returned an unrelated P11 statement about dataset taxonomy; U06 returned `P05 [P05]` instead of acknowledging that the full BrowseComp evaluation was not performed. Therefore, “answered” is output coverage, not correctness. Keyword matching is a lexical heuristic, not semantic accuracy. `human_review_blank.csv` has deliberately unfilled human-review fields. The seven independent auditor challenges all matched expected mechanical outcomes, including a deliberately false claim paired with a real quotation passing the checker.

Independent dense retrieval with the original questions retrieved the expected source in the top three for all 20 answerable cases, including after the cosine threshold of 0.30. This is performance on an authored small corpus, not evidence of general retrieval accuracy. Full-agent queries can be rewritten, unlike basic-RAG queries: this is an end-to-end variant comparison, not a pure audit-only causal ablation.

All four external-tool cases had correct predicted routes, actual attempted dispatch, and successful upstream completion. Three responses were live and one was cached. Successful dispatch/API completion does not guarantee fulfillment of every requested answer detail. Two separate audit-intent cases invoked the automatic auditor node; the node is not an action the LLM planner can select. Direct mechanical correctness is measured by `auditor_challenges.json`, not by those invocation counts.

U06 in full-agent mode took 301.937 seconds wall time; its generation trace records 300.896 seconds. The observation is retained in all latency statistics; no causal explanation is established by the evaluation. This outlier accounts for the large mean/median difference. Both statistics should be reported together. The remaining raw traces and all cache statuses are preserved.

Models: Qwen3-0.6B-Q4_K_M and all-MiniLM-L6-v2-Q8_0 (384-dimensional embeddings), served by llama.cpp b11899. Exact quantization SHA-256 values, code/corpus/case hashes, temperature 0, seed 42, token limits, package versions, and timestamps are in `run_metadata.json`. Offline verification passed 41/41 tests in the observed 0.353-second run. The results support a transparent small system demonstration and reveal reliability limitations; they do not establish state-of-the-art performance or broad semantic accuracy.
