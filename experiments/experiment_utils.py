"""
Shared helpers for experiment tracing and result serialization.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List

from core.agent import CacheAwareAgent, CacheMetrics


def metrics_to_dict(metrics: CacheMetrics) -> Dict[str, Any]:
    return {
        "prompt_tokens": metrics.prompt_tokens,
        "completion_tokens": metrics.completion_tokens,
        "cache_hit_tokens": metrics.cache_hit_tokens,
        "cache_miss_tokens": metrics.cache_miss_tokens,
        "cache_hit_rate": metrics.cache_hit_rate,
        "cost": metrics.cost_estimate,
    }


def aggregate_metric_dicts(metric_dicts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate numeric metric dictionaries across repeated runs."""
    if not metric_dicts:
        return {}

    aggregated: Dict[str, Any] = {}
    keys = metric_dicts[0].keys()
    for key in keys:
        values = [metrics[key] for metrics in metric_dicts]
        if all(isinstance(value, (int, float)) for value in values):
            mean = sum(values) / len(values)
            variance = sum((value - mean) ** 2 for value in values) / len(values)
            aggregated[key] = {
                "mean": mean,
                "std": variance**0.5,
                "min": min(values),
                "max": max(values),
            }
        else:
            aggregated[key] = values
    return aggregated


def aggregate_count_dicts(count_dicts: List[Dict[str, int]]) -> Dict[str, Dict[str, float]]:
    """Aggregate count dictionaries across repeated runs."""
    if not count_dicts:
        return {}

    all_keys = sorted({key for count_dict in count_dicts for key in count_dict})
    aggregated: Dict[str, Dict[str, float]] = {}
    for key in all_keys:
        values = [count_dict.get(key, 0) for count_dict in count_dicts]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        aggregated[key] = {
            "mean": mean,
            "std": variance**0.5,
            "min": min(values),
            "max": max(values),
        }
    return aggregated


def aggregate_per_turn_metrics(per_turn_runs: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Aggregate aligned per-turn metric lists across repeated runs."""
    if not per_turn_runs:
        return []

    turn_count = len(per_turn_runs[0])
    aggregated_turns: List[Dict[str, Any]] = []

    for turn_index in range(turn_count):
        turn_metrics = []
        for run in per_turn_runs:
            if len(run) != turn_count:
                return []
            turn_metrics.append({key: value for key, value in run[turn_index].items() if key != "turn"})

        aggregated_turns.append(
            {
                "turn": per_turn_runs[0][turn_index]["turn"],
                **aggregate_metric_dicts(turn_metrics),
            }
        )

    return aggregated_turns


def summarize_turn_traces(turn_traces: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize tool-loop observability from per-turn traces."""
    tool_name_counts: Counter[str] = Counter()
    error_code_counts: Counter[str] = Counter()
    pending_tool_name_counts: Counter[str] = Counter()

    metrics = {
        "turn_count": len(turn_traces),
        "turns_with_tool_calls": 0,
        "turns_with_tool_execution": 0,
        "turns_with_tool_errors": 0,
        "turns_terminated_by_max_rounds": 0,
        "total_tool_calls": 0,
        "total_tool_executions": 0,
        "successful_tool_executions": 0,
        "failed_tool_executions": 0,
        "total_pending_tool_calls_after_loop": 0,
        "total_tool_rounds_executed": 0,
        "total_completion_rounds": 0,
    }

    for record in turn_traces:
        trace = record.get("trace") or {}
        tool_execution_results = trace.get("tool_execution_results", [])
        pending_tool_names = trace.get("pending_tool_names_after_loop", [])

        metrics["total_tool_calls"] += trace.get("tool_call_count", 0)
        metrics["total_tool_executions"] += trace.get("tool_execution_count", len(tool_execution_results))
        metrics["total_pending_tool_calls_after_loop"] += trace.get("pending_tool_calls_after_loop", 0)
        metrics["total_tool_rounds_executed"] += trace.get("tool_rounds_executed", 0)
        metrics["total_completion_rounds"] += trace.get("completion_round_count", 1)

        if trace.get("tool_call_count", 0) > 0:
            metrics["turns_with_tool_calls"] += 1
        if trace.get("tool_execution_count", len(tool_execution_results)) > 0:
            metrics["turns_with_tool_execution"] += 1
        if trace.get("tool_loop_terminated_by_max_rounds"):
            metrics["turns_terminated_by_max_rounds"] += 1

        turn_had_error = False
        for item in tool_execution_results:
            tool_name = item.get("tool_name")
            if tool_name:
                tool_name_counts[tool_name] += 1

            if item.get("success"):
                metrics["successful_tool_executions"] += 1
            else:
                metrics["failed_tool_executions"] += 1
                turn_had_error = True
                error = item.get("error") or {}
                error_code = error.get("code")
                if error_code:
                    error_code_counts[error_code] += 1

        if turn_had_error:
            metrics["turns_with_tool_errors"] += 1

        for tool_name in pending_tool_names:
            pending_tool_name_counts[tool_name] += 1

    total_tool_executions = metrics["total_tool_executions"]
    total_turns = metrics["turn_count"]
    metrics["tool_success_rate"] = (
        metrics["successful_tool_executions"] / total_tool_executions if total_tool_executions else 0.0
    )
    metrics["tool_error_rate"] = (
        metrics["failed_tool_executions"] / total_tool_executions if total_tool_executions else 0.0
    )
    metrics["max_round_termination_rate"] = (
        metrics["turns_terminated_by_max_rounds"] / total_turns if total_turns else 0.0
    )
    metrics["avg_tool_executions_per_turn"] = (
        total_tool_executions / total_turns if total_turns else 0.0
    )
    metrics["avg_completion_rounds_per_turn"] = (
        metrics["total_completion_rounds"] / total_turns if total_turns else 0.0
    )

    return {
        "metrics": metrics,
        "tool_name_counts": dict(sorted(tool_name_counts.items())),
        "error_code_counts": dict(sorted(error_code_counts.items())),
        "pending_tool_name_counts": dict(sorted(pending_tool_name_counts.items())),
    }


def summarize_result_runs(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a compact statistical summary across repeated runs."""
    if not runs:
        return {}

    summary: Dict[str, Any] = {
        "run_count": len(runs),
        "aggregate_total_metrics": aggregate_metric_dicts(
            [run["total_metrics"] for run in runs]
        ),
    }

    if all("per_turn_metrics" in run for run in runs):
        summary["aggregate_per_turn_metrics"] = aggregate_per_turn_metrics(
            [run["per_turn_metrics"] for run in runs]
        )

    if all("tool_observability" in run for run in runs):
        summary["aggregate_tool_observability"] = {
            "metrics": aggregate_metric_dicts(
                [run["tool_observability"]["metrics"] for run in runs]
            ),
            "tool_name_counts": aggregate_count_dicts(
                [run["tool_observability"]["tool_name_counts"] for run in runs]
            ),
            "error_code_counts": aggregate_count_dicts(
                [run["tool_observability"]["error_code_counts"] for run in runs]
            ),
            "pending_tool_name_counts": aggregate_count_dicts(
                [run["tool_observability"]["pending_tool_name_counts"] for run in runs]
            ),
        }

    return summary


def build_turn_record(turn: int, question: str, result: Dict[str, Any], preview_chars: int = 150) -> Dict[str, Any]:
    content = result.get("content") or ""
    trace = result.get("trace") or {}
    return {
        "turn": turn,
        "question": question,
        "response_preview": content[:preview_chars],
        "response_chars": len(content),
        "metrics": metrics_to_dict(result["metrics"]),
        "trace": trace,
    }


def run_turn_sequence(
    agent: CacheAwareAgent,
    questions: Iterable[str],
    verbose: bool = False,
    preview_chars: int = 150,
) -> Dict[str, Any]:
    turn_records: List[Dict[str, Any]] = []

    for turn, question in enumerate(questions, 1):
        print(f"[Turn {turn}] User: {question}")
        result = agent.send_message(question, verbose=verbose)
        preview = (result["content"] or "")[:preview_chars]
        print(f"[Turn {turn}] Assistant: {preview}...\n")
        turn_records.append(build_turn_record(turn, question, result, preview_chars=preview_chars))

    total_metrics = agent.get_total_metrics()
    tool_observability = summarize_turn_traces(turn_records)
    return {
        "total_metrics": metrics_to_dict(total_metrics),
        "per_turn_metrics": [
            {
                "turn": record["turn"],
                **record["metrics"],
            }
            for record in turn_records
        ],
        "turn_traces": turn_records,
        "tool_observability": tool_observability,
    }


def build_agent_config(agent: CacheAwareAgent, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    config = {
        "session": agent.session_config.to_dict(),
        "enable_tools": agent.enable_tools,
        "max_tool_rounds": agent.max_tool_rounds,
        "registered_tool_count": len(agent.tool_cache),
        "enabled_tool_names": [schema["function"]["name"] for schema in agent._get_enabled_tool_schemas()],
    }
    if extra:
        config.update(extra)
    return config
