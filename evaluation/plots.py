"""Standalone scientific summary plots with explicit metric scope."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def create_plots(directory, summary):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "savefig.dpi": 200})
    names = ["Closed-book LLM", "Basic RAG", "Full agent"]
    variants = [summary["variants"][mode] for mode in ("llm", "basic", "agent")]
    x = np.arange(3)
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4), layout="constrained")
    for ax, key, title, count in [(axes[0], "answerable_coverage", "Answered corpus questions (n=20)", "answerable_answered"),
                                   (axes[1], "unanswerable_abstention_rate", "Abstained on missing evidence (n=6)", "unanswerable_abstained")]:
        bars = ax.bar(x, [v[key] or 0 for v in variants], color=["#94a3b8", "#38bdf8", "#0f766e"], width=.6)
        ax.set_xticks(x, names, rotation=10)
        ax.set_ylim(0, 1.16)
        ax.set_yticks([0, .25, .5, .75, 1], ["0%", "25%", "50%", "75%", "100%"])
        ax.set_title(title, fontsize=11)
        ax.bar_label(bars, labels=[f"{v[count]}/{v['answerable_cases'] if count == 'answerable_answered' else v['unanswerable_cases']}" for v in variants], padding=3)
    fig.savefig(directory / "coverage_abstention.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(6.4, 4.0), layout="constrained")
    rag = variants[1:]
    positions = np.arange(2)
    for offset, key, label, color, numerator, denominator in [(-.18, "generated_mechanical_validity", "Raw generated claims", "#38bdf8", "generated_valid_claims", "generated_claims"),
                                                              (.18, "delivered_mechanical_validity", "Delivered claims", "#0f766e", "delivered_valid_claims", "delivered_claims")]:
        bars = ax.bar(positions + offset, [v[key] or 0 for v in rag], width=.34, color=color, label=label)
        ax.bar_label(bars, labels=[f"{v[numerator]}/{v[denominator]}" if v[denominator] else "N/A (0 claims)" for v in rag], padding=3, fontsize=9)
    ax.set_xticks(positions, names[1:])
    ax.set_ylim(0, 1.24)
    ax.set_yticks([0, .25, .5, .75, 1], ["0%", "25%", "50%", "75%", "100%"])
    ax.set_title("Source-ID + quote validity (26 content cases)")
    ax.set_ylabel("Mechanically valid claims / all claims")
    ax.legend(loc="upper center", bbox_to_anchor=(.5, 1.02), ncol=2, fontsize=8)
    ax.set_xlabel("Mechanical validity does not establish semantic truth.\nClosed-book source validity is N/A.", fontsize=8, labelpad=12)
    fig.savefig(directory / "claim_validity.png", bbox_inches="tight")
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4), layout="constrained")
    bars = axes[0].bar(x, [v["keyword_complete_rate_heuristic"] or 0 for v in variants], color=["#94a3b8", "#38bdf8", "#0f766e"], width=.6)
    axes[0].set_title("All keyword groups found (n=20)", fontsize=11)
    axes[0].set_ylim(0, 1.16)
    axes[0].set_yticks([0, .5, 1], ["0%", "50%", "100%"])
    axes[0].bar_label(bars, labels=[f"{v['keyword_complete_count_heuristic']}/20" for v in variants], padding=3)
    axes[0].set_ylabel("Lexical heuristic; not semantic accuracy")
    for offset, metric, label, color in [(-.18, "latency_median_seconds", "Median", "#38bdf8"),
                                         (.18, "latency_mean_seconds", "Mean", "#0f766e")]:
        bars = axes[1].bar(x + offset, [v[metric] or 0 for v in variants], width=.34, color=color, label=label)
        axes[1].bar_label(bars, fmt="%.2f", padding=3, fontsize=8)
    axes[1].set_title("End-to-end content latency", fontsize=11)
    axes[1].set_ylabel("Seconds / request (26 per variant)")
    axes[1].set_ylim(0, max(v["latency_mean_seconds"] or 0 for v in variants) * 1.28)
    axes[1].legend(loc="upper left", fontsize=8)
    axes[1].text(.97, .95, "301.94 s full-agent outlier retained", transform=axes[1].transAxes, ha="right", va="top", fontsize=8)
    for ax in axes:
        ax.set_xticks(x, names, rotation=10)
    fig.savefig(directory / "keyword_latency.png")
    plt.close(fig)
