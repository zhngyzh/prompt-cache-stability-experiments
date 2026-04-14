"""
Multi-turn tool orchestration experiment.

This experiment tests how cache performance changes when agents need to make
multiple tool calls across several rounds to complete a task.

Scenario:
1. List directory contents
2. Read a specific file
3. Summarize findings with echo_json

We compare max_tool_rounds=1/2/3 to see how tool orchestration depth affects
cache hit rates and costs.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent import CacheAwareAgent
from experiments.experiment_utils import build_agent_config, run_turn_sequence, summarize_result_runs


DEFAULT_RESULTS_DIR = Path("results")
OUTPUT_FILENAME = "multi_turn_tools_results.json"

# Questions designed to trigger multi-step tool usage
MULTI_TURN_QUESTIONS = [
    "List the files in the current directory and read README.md",
    "Find and read the core/agent.py file",
    "List files in the experiments directory and summarize what you find",
    "Read the requirements.txt file and tell me what dependencies are listed",
    "Check what's in the tests directory and read one test file",
]

BASE_AGENT_KWARGS = {
    "model": "deepseek-chat",
    "temperature": 0.7,
    "max_tokens": 1024,
    "enable_tools": True,
}


def create_multi_turn_agent(max_tool_rounds: int) -> CacheAwareAgent:
    return CacheAwareAgent(**BASE_AGENT_KWARGS, max_tool_rounds=max_tool_rounds)


def resolve_output_file(output_dir: Path) -> Path:
    return output_dir / OUTPUT_FILENAME


def build_experiment_metadata(num_turns: int, max_tool_rounds: int) -> Dict[str, Any]:
    return {
        "questions": MULTI_TURN_QUESTIONS[:num_turns],
        "track": "multi_turn_tools",
        "max_tool_rounds": max_tool_rounds,
        "agent_kwargs": {**BASE_AGENT_KWARGS, "max_tool_rounds": max_tool_rounds},
    }


def print_run_summary(run_data: Dict[str, Any]) -> None:
    total_metrics = run_data["total_metrics"]
    tool_obs = run_data["tool_observability"]["metrics"]

    print()
    print("=" * 80)
    print("Experiment Results")
    print("=" * 80)
    print()

    print("Total Metrics:")
    print(f"  Prompt Tokens: {total_metrics['prompt_tokens']:,}")
    print(f"  Completion Tokens: {total_metrics['completion_tokens']:,}")
    print(f"  Cache Hit Tokens: {total_metrics['cache_hit_tokens']:,}")
    print(f"  Cache Miss Tokens: {total_metrics['cache_miss_tokens']:,}")
    print(f"  Cache Hit Rate: {total_metrics['cache_hit_rate']:.1%}")
    print(f"  Total Cost: ${total_metrics['cost']:.6f}")

    print("\nTool Observability:")
    print(f"  Tool Execution Count: {tool_obs['total_tool_executions']}")
    print(f"  Tool Success Rate: {tool_obs['tool_success_rate']:.1%}")
    print(f"  Truncated by max_tool_rounds: {tool_obs['turns_terminated_by_max_rounds']}")
    tool_name_counts = run_data["tool_observability"].get("tool_name_counts", {})
    error_code_counts = run_data["tool_observability"].get("error_code_counts", {})
    if tool_name_counts:
        print(f"  Tools Executed: {', '.join(tool_name_counts.keys())}")
    if error_code_counts:
        print(f"  Error Codes: {error_code_counts}")

    print("\nPer-Turn Analysis:")
    print(f"{'Turn':<6} {'Hit':<10} {'Miss':<10} {'Rate':<8} {'Cost':<12} {'Tools':<6}")
    print("-" * 64)
    for turn_metrics in run_data["per_turn_metrics"]:
        turn_num = turn_metrics['turn']
        trace = run_data["turn_traces"][turn_num - 1]
        tool_count = trace["trace"].get("tool_execution_count", 0)
        print(
            f"{turn_num:<6} "
            f"{turn_metrics['cache_hit_tokens']:<10,} "
            f"{turn_metrics['cache_miss_tokens']:<10,} "
            f"{turn_metrics['cache_hit_rate']:<7.1%} "
            f"${turn_metrics['cost']:<11.6f} "
            f"{tool_count:<6}"
        )


def print_comparison_summary(results: Dict[str, Any]) -> None:
    print()
    print("=" * 80)
    print("Multi-Turn Tool Orchestration Comparison")
    print("=" * 80)
    print()

    configs = results["configurations"]

    print(f"{'Config':<20} {'Hit Rate':<20} {'Cost':<20} {'Tool Exec':<15}")
    print("-" * 75)

    for config_name, config_data in configs.items():
        summary = config_data["summary"]
        metrics = summary["aggregate_total_metrics"]
        tool_obs = summary["aggregate_tool_observability"]

        hit_rate = f"{metrics['cache_hit_rate']['mean']:.2%} +/- {metrics['cache_hit_rate']['std']:.2%}"
        cost = f"${metrics['cost']['mean']:.4f} +/- ${metrics['cost']['std']:.4f}"
        tool_exec = f"{tool_obs.get('total_tool_executions', {}).get('mean', 0):.1f}"

        print(f"{config_name:<20} {hit_rate:<20} {cost:<20} {tool_exec:<15}")


def run_single_configuration(
    max_tool_rounds: int,
    num_turns: int,
    run_id: int,
    seed: int,
) -> Dict[str, Any]:
    random.seed(seed)

    print("=" * 80)
    print(f"Multi-Turn Tools Experiment: max_tool_rounds={max_tool_rounds} (Run {run_id})")
    print("=" * 80)
    print()

    agent = create_multi_turn_agent(max_tool_rounds=max_tool_rounds)

    if run_id == 1:
        print("Session Config (Latched):")
        print(json.dumps(agent.session_config.to_dict(), indent=2))
        print()

        print(f"Tool Cache: {len(agent.tool_cache)} tools registered")
        print(f"Max Tool Rounds: {agent.max_tool_rounds}")
        print()

    print(f"Running {num_turns} turns...")
    print("-" * 80)

    run_data = run_turn_sequence(agent, MULTI_TURN_QUESTIONS[:num_turns], verbose=True, preview_chars=200)

    return {
        "experiment": "multi_turn_tools",
        "schema_version": "v3",
        "run_id": run_id,
        "seed": seed,
        "num_turns": num_turns,
        "max_tool_rounds": max_tool_rounds,
        "config": build_agent_config(
            agent,
            extra={
                **build_experiment_metadata(num_turns, max_tool_rounds),
                "run_id": run_id,
                "seed": seed,
            },
        ),
        **run_data,
    }


def run_multi_turn_experiment(
    num_turns: int = 5,
    repeats: int = 1,
    seed: int = 42,
    output_dir: Path = DEFAULT_RESULTS_DIR,
    max_tool_rounds_configs: List[int] | None = None,
) -> Dict[str, Any]:
    if max_tool_rounds_configs is None:
        max_tool_rounds_configs = [1, 2, 3]

    all_configurations = {}

    for max_rounds in max_tool_rounds_configs:
        config_name = f"max_rounds_{max_rounds}"
        print(f"\n{'=' * 80}")
        print(f"Testing Configuration: {config_name}")
        print(f"{'=' * 80}\n")

        runs = [
            run_single_configuration(
                max_tool_rounds=max_rounds,
                num_turns=num_turns,
                run_id=index + 1,
                seed=seed + index,
            )
            for index in range(repeats)
        ]

        if repeats == 1:
            config_results = runs[0]
            print_run_summary(config_results)
        else:
            config_results = {
                "max_tool_rounds": max_rounds,
                "num_turns": num_turns,
                "repeat_count": repeats,
                "base_seed": seed,
                "config": build_experiment_metadata(num_turns, max_rounds),
                "summary": summarize_result_runs(runs),
                "runs": runs,
            }

        all_configurations[config_name] = config_results

    results = {
        "experiment": "multi_turn_tools",
        "schema_version": "v3",
        "num_turns": num_turns,
        "repeat_count": repeats,
        "base_seed": seed,
        "max_tool_rounds_tested": max_tool_rounds_configs,
        "configurations": all_configurations,
    }

    if repeats > 1:
        print_comparison_summary(results)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = resolve_output_file(output_dir)
    output_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults saved to: {output_file}")
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run multi-turn tool orchestration experiment.")
    parser.add_argument(
        "--turns",
        type=int,
        default=5,
        help="Number of turns to run in each experiment.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for repeatable runs.",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="How many repeated runs to execute.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_RESULTS_DIR),
        help="Directory where result artifacts should be written.",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        nargs="+",
        default=[1, 2, 3],
        help="List of max_tool_rounds values to test (e.g., --max-rounds 1 2 3).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_multi_turn_experiment(
        num_turns=args.turns,
        repeats=args.repeats,
        seed=args.seed,
        output_dir=Path(args.output_dir),
        max_tool_rounds_configs=args.max_rounds,
    )
