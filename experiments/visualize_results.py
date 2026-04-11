"""
Generate presentation-friendly charts and summaries from experiment results.

This script supports:
- legacy single-list cache breaker results
- split-track single-run results
- split-track repeated results with summary statistics
"""

from __future__ import annotations

import json
import argparse
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RESULTS_DIR = ROOT / "results"
BASELINE_FILENAME = "baseline_results.json"
CACHE_BUSTERS_FILENAME = "cache_busters_results.json"
SUMMARY_FILENAME = "experiment_summary.md"
OVERVIEW_FIGURE_FILENAME = "cache_overview.png"
BASELINE_TURNS_FIGURE_FILENAME = "baseline_turns.png"


def load_json(path: Path) -> dict[str, Any] | list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_results_paths(results_dir: Path) -> dict[str, Path]:
    figures_dir = results_dir / "figures"
    return {
        "baseline_file": results_dir / BASELINE_FILENAME,
        "cache_busters_file": results_dir / CACHE_BUSTERS_FILENAME,
        "summary_file": results_dir / SUMMARY_FILENAME,
        "overview_figure": figures_dir / OVERVIEW_FIGURE_FILENAME,
        "baseline_turns_figure": figures_dir / BASELINE_TURNS_FIGURE_FILENAME,
    }


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def extract_metric_bundle(container: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize metrics from either:
    - single-run shape: {"total_metrics": {...}}
    - repeated-run shape: {"summary": {"aggregate_total_metrics": {...}}}
    """

    if "total_metrics" in container:
        metrics = container["total_metrics"]
        return {
            "hit_rate": metrics["cache_hit_rate"],
            "hit_rate_std": 0.0,
            "cost": metrics["cost"],
            "cost_std": 0.0,
            "cache_hit_tokens": metrics["cache_hit_tokens"],
            "cache_hit_tokens_std": 0.0,
            "cache_miss_tokens": metrics["cache_miss_tokens"],
            "cache_miss_tokens_std": 0.0,
        }

    summary = container["summary"]["aggregate_total_metrics"]
    return {
        "hit_rate": summary["cache_hit_rate"]["mean"],
        "hit_rate_std": summary["cache_hit_rate"]["std"],
        "cost": summary["cost"]["mean"],
        "cost_std": summary["cost"]["std"],
        "cache_hit_tokens": summary["cache_hit_tokens"]["mean"],
        "cache_hit_tokens_std": summary["cache_hit_tokens"]["std"],
        "cache_miss_tokens": summary["cache_miss_tokens"]["mean"],
        "cache_miss_tokens_std": summary["cache_miss_tokens"]["std"],
    }


def extract_tool_observability_bundle(container: dict[str, Any]) -> dict[str, Any] | None:
    if "tool_observability" in container:
        return container["tool_observability"]
    summary = container.get("summary", {})
    return summary.get("aggregate_tool_observability")


def build_legacy_rows(
    baseline: dict[str, Any], cache_busters: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    baseline_metrics = extract_metric_bundle(baseline)
    rows = [
        {
            "group": "legacy",
            "label": "Baseline",
            **baseline_metrics,
            "delta_hit": 0.0,
            "delta_cost": 0.0,
        }
    ]

    for item in cache_busters:
        metrics = extract_metric_bundle(item)
        rows.append(
            {
                "group": "legacy",
                "label": item["scenario"],
                **metrics,
                "delta_hit": metrics["hit_rate"] - baseline_metrics["hit_rate"],
                "delta_cost": metrics["cost"] - baseline_metrics["cost"],
            }
        )
    return rows


def build_track_rows(cache_busters: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for track_name, track_data in cache_busters["tracks"].items():
        baseline_metrics = extract_metric_bundle(track_data["baseline"])
        rows.append(
            {
                "group": track_name,
                "label": f"{track_name} / Baseline",
                **baseline_metrics,
                "delta_hit": 0.0,
                "delta_cost": 0.0,
            }
        )

        for item in track_data["scenarios"]:
            metrics = extract_metric_bundle(item)
            rows.append(
                {
                    "group": track_name,
                    "label": f"{track_name} / {item['scenario']}",
                    **metrics,
                    "delta_hit": metrics["hit_rate"] - baseline_metrics["hit_rate"],
                    "delta_cost": metrics["cost"] - baseline_metrics["cost"],
                }
            )

    return rows


def build_comparison_rows(
    baseline: dict[str, Any], cache_busters: dict[str, Any] | list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if isinstance(cache_busters, list):
        return build_legacy_rows(baseline, cache_busters)
    return build_track_rows(cache_busters)


def plot_overview(rows: list[dict[str, Any]], output_path: Path) -> None:
    labels = [row["label"] for row in rows]
    hit_rates = [row["hit_rate"] * 100 for row in rows]
    hit_rate_stds = [row["hit_rate_std"] * 100 for row in rows]
    costs = [row["cost"] for row in rows]
    cost_stds = [row["cost_std"] for row in rows]
    colors = ["#2f6bff" if "Baseline" in row["label"] else "#ef6c57" for row in rows]

    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    fig.suptitle("Cache-Aware Agent Experiment Overview", fontsize=16, fontweight="bold")

    axes[0].barh(labels, hit_rates, color=colors, xerr=hit_rate_stds, ecolor="#1f1f1f", capsize=3)
    axes[0].invert_yaxis()
    axes[0].set_title("Cache Hit Rate")
    axes[0].set_xlabel("Hit Rate (%)")
    axes[0].set_xlim(0, 100)
    for index, value in enumerate(hit_rates):
        std = hit_rate_stds[index]
        suffix = f" +/- {std:.2f}" if std > 0 else ""
        axes[0].text(min(value + 1, 99.2), index, f"{value:.2f}%{suffix}", va="center", fontsize=9)

    axes[1].barh(labels, costs, color=colors, xerr=cost_stds, ecolor="#1f1f1f", capsize=3)
    axes[1].invert_yaxis()
    axes[1].set_title("Estimated Cost")
    axes[1].set_xlabel("Cost (USD)")
    max_cost = max(costs) if costs else 0.0
    axes[1].set_xlim(0, max_cost * 1.25 if max_cost else 1)
    for index, value in enumerate(costs):
        std = cost_stds[index]
        suffix = f" +/- {std:.4f}" if std > 0 else ""
        axes[1].text(value + max_cost * 0.02, index, f"${value:.4f}{suffix}", va="center", fontsize=9)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_baseline_turns(baseline: dict[str, Any], output_path: Path) -> None:
    if "per_turn_metrics" in baseline:
        metrics = baseline["per_turn_metrics"]
        turns = [item["turn"] for item in metrics]
        hit_rates = [item["cache_hit_rate"] * 100 for item in metrics]
        costs = [item["cost"] for item in metrics]
    else:
        metrics = baseline.get("summary", {}).get("aggregate_per_turn_metrics", [])
        turns = [item["turn"] for item in metrics]
        hit_rates = [item["cache_hit_rate"]["mean"] * 100 for item in metrics]
        costs = [item["cost"]["mean"] for item in metrics]

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    fig.suptitle("Baseline Per-Turn Trends", fontsize=16, fontweight="bold")

    axes[0].plot(turns, hit_rates, marker="o", color="#2f6bff", linewidth=2)
    axes[0].set_ylabel("Hit Rate (%)")
    axes[0].set_ylim(0, 100)
    axes[0].grid(alpha=0.3)

    axes[1].plot(turns, costs, marker="o", color="#ef6c57", linewidth=2)
    axes[1].set_ylabel("Cost (USD)")
    axes[1].set_xlabel("Turn")
    axes[1].grid(alpha=0.3)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def format_percent_with_std(value: float, std: float) -> str:
    if std > 0:
        return f"{value:.2%} +/- {std:.2%}"
    return f"{value:.2%}"


def format_cost_with_std(value: float, std: float) -> str:
    if std > 0:
        return f"${value:.4f} +/- ${std:.4f}"
    return f"${value:.4f}"


def format_number_with_std(value: float, std: float, precision: int = 2) -> str:
    if std > 0:
        return f"{value:.{precision}f} +/- {std:.{precision}f}"
    return f"{value:.{precision}f}"


def format_tool_count_map(counts: dict[str, Any]) -> str:
    if not counts:
        return "none"

    parts = []
    for key, value in counts.items():
        if isinstance(value, dict):
            parts.append(f"`{key}` {format_number_with_std(value['mean'], value['std'])}")
        else:
            parts.append(f"`{key}` {value}")
    return ", ".join(parts)


def build_tool_observability_section(label: str, bundle: dict[str, Any]) -> list[str]:
    metrics = bundle["metrics"]
    aggregated = isinstance(metrics.get("total_tool_executions"), dict)

    def metric_value(name: str) -> tuple[float, float]:
        value = metrics[name]
        if aggregated:
            return value["mean"], value["std"]
        return float(value), 0.0

    total_tool_executions, total_tool_executions_std = metric_value("total_tool_executions")
    tool_success_rate, tool_success_rate_std = metric_value("tool_success_rate")
    turns_terminated, turns_terminated_std = metric_value("turns_terminated_by_max_rounds")
    pending_tool_calls, pending_tool_calls_std = metric_value("total_pending_tool_calls_after_loop")

    return [
        f"### {label}",
        "",
        f"- Tool executions: {format_number_with_std(total_tool_executions, total_tool_executions_std)}",
        f"- Tool success rate: {format_percent_with_std(tool_success_rate, tool_success_rate_std)}",
        f"- Max-round terminations: {format_number_with_std(turns_terminated, turns_terminated_std)}",
        f"- Pending tool calls after loop: {format_number_with_std(pending_tool_calls, pending_tool_calls_std)}",
        f"- Executed tools: {format_tool_count_map(bundle.get('tool_name_counts', {}))}",
        f"- Error codes: {format_tool_count_map(bundle.get('error_code_counts', {}))}",
        "",
    ]


def build_tool_observability_sections(
    baseline: dict[str, Any],
    cache_busters: dict[str, Any] | list[dict[str, Any]],
) -> list[str]:
    sections: list[str] = []

    baseline_bundle = extract_tool_observability_bundle(baseline)
    if baseline_bundle:
        baseline_metrics = baseline_bundle["metrics"]
        baseline_exec = baseline_metrics["total_tool_executions"]
        if isinstance(baseline_exec, dict):
            baseline_exec = baseline_exec["mean"]
        if baseline_exec > 0:
            sections.extend(build_tool_observability_section("baseline", baseline_bundle))

    if isinstance(cache_busters, list):
        return sections

    for track_name, track_data in cache_busters["tracks"].items():
        baseline_bundle = extract_tool_observability_bundle(track_data["baseline"])
        if baseline_bundle:
            baseline_exec = baseline_bundle["metrics"]["total_tool_executions"]
            if isinstance(baseline_exec, dict):
                baseline_exec = baseline_exec["mean"]
            if baseline_exec > 0:
                sections.extend(
                    build_tool_observability_section(
                        f"{track_name} / Baseline",
                        baseline_bundle,
                    )
                )

        for scenario in track_data["scenarios"]:
            bundle = extract_tool_observability_bundle(scenario)
            if not bundle:
                continue
            total_exec = bundle["metrics"]["total_tool_executions"]
            if isinstance(total_exec, dict):
                total_exec = total_exec["mean"]
            if total_exec <= 0 and not bundle.get("error_code_counts") and not bundle.get("pending_tool_name_counts"):
                continue
            sections.extend(
                build_tool_observability_section(
                    f"{track_name} / {scenario['scenario']}",
                    bundle,
                )
            )

    return sections


def write_summary(
    rows: list[dict[str, Any]],
    output_path: Path,
    baseline: dict[str, Any],
    cache_busters: dict[str, Any] | list[dict[str, Any]],
) -> None:
    lines = ["# Experiment Summary", ""]
    groups = sorted({row["group"] for row in rows})

    for group in groups:
        group_rows = [row for row in rows if row["group"] == group]
        lines.extend(
            [
                f"## {group}",
                "",
                "| Scenario | Hit Rate | Delta vs Baseline | Cost | Delta Cost | Cache Hit Tokens | Cache Miss Tokens |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )

        for row in group_rows:
            hit_rate_text = format_percent_with_std(row["hit_rate"], row["hit_rate_std"])
            cost_text = format_cost_with_std(row["cost"], row["cost_std"])
            lines.append(
                "| {label} | {hit_rate_text} | {delta_hit:+.2%} | {cost_text} | ${delta_cost:+.4f} | {cache_hit_tokens:,.0f} | {cache_miss_tokens:,.0f} |".format(
                    label=row["label"],
                    hit_rate_text=hit_rate_text,
                    delta_hit=row["delta_hit"],
                    cost_text=cost_text,
                    delta_cost=row["delta_cost"],
                    cache_hit_tokens=row["cache_hit_tokens"],
                    cache_miss_tokens=row["cache_miss_tokens"],
                )
            )

        strongest_drop = min(
            [row for row in group_rows if "Baseline" not in row["label"]],
            key=lambda item: item["delta_hit"],
            default=None,
        )
        if strongest_drop:
            lines.extend(
                [
                    "",
                    f"Key takeaway: **{strongest_drop['label']}** shows the largest drop in this track.",
                    "",
                ]
            )

    tool_sections = build_tool_observability_sections(baseline, cache_busters)
    if tool_sections:
        lines.extend(["## Tool Observability", ""])
        lines.extend(tool_sections)

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate charts and summaries from experiment results.")
    parser.add_argument(
        "--results-dir",
        default=str(DEFAULT_RESULTS_DIR),
        help="Directory containing baseline/cache_busters result files and where derived artifacts should be written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results_dir = Path(args.results_dir)
    if not results_dir.is_absolute():
        results_dir = ROOT / results_dir
    paths = resolve_results_paths(results_dir)

    baseline = load_json(paths["baseline_file"])
    cache_busters = load_json(paths["cache_busters_file"])

    rows = build_comparison_rows(baseline, cache_busters)
    plot_overview(rows, paths["overview_figure"])
    plot_baseline_turns(baseline, paths["baseline_turns_figure"])
    write_summary(rows, paths["summary_file"], baseline, cache_busters)

    print("Generated artifacts:")
    print(f"- {display_path(paths['overview_figure'])}")
    print(f"- {display_path(paths['baseline_turns_figure'])}")
    print(f"- {display_path(paths['summary_file'])}")


if __name__ == "__main__":
    main()
