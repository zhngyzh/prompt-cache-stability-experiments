"""
Baseline experiment for the cache-aware agent.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent import CacheAwareAgent
from experiments.experiment_utils import build_agent_config, run_turn_sequence, summarize_result_runs


DEFAULT_RESULTS_DIR = Path("results")
OUTPUT_FILENAME = "baseline_results.json"

BASELINE_QUESTIONS = [
    "What is prompt caching?",
    "How does the four-layer architecture work?",
    "What is the BOUNDARY marker for?",
    "Explain append-only message management",
    "Why is tool definition caching important?",
    "What is Latch configuration?",
    "How does deterministic serialization help?",
    "What happens if we modify message history?",
    "Why should we avoid changing tools mid-session?",
    "Summarize the key cache optimization strategies",
]

BASELINE_AGENT_KWARGS = {
    "model": "deepseek-chat",
    "temperature": 0.7,
    "max_tokens": 1024,
    "enable_tools": False,
}


def create_baseline_agent() -> CacheAwareAgent:
    return CacheAwareAgent(**BASELINE_AGENT_KWARGS)


def resolve_output_file(output_dir: Path) -> Path:
    return output_dir / OUTPUT_FILENAME


def build_baseline_metadata(num_turns: int) -> Dict[str, Any]:
    return {
        "questions": BASELINE_QUESTIONS[:num_turns],
        "track": "baseline",
        "agent_kwargs": BASELINE_AGENT_KWARGS,
    }


def print_run_summary(run_data: Dict[str, Any]) -> None:
    total_metrics = run_data["total_metrics"]

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

    print("\nPer-Turn Analysis:")
    print(f"{'Turn':<6} {'Hit':<10} {'Miss':<10} {'Rate':<8} {'Cost':<12}")
    print("-" * 56)
    for turn_metrics in run_data["per_turn_metrics"]:
        print(
            f"{turn_metrics['turn']:<6} "
            f"{turn_metrics['cache_hit_tokens']:<10,} "
            f"{turn_metrics['cache_miss_tokens']:<10,} "
            f"{turn_metrics['cache_hit_rate']:<7.1%} "
            f"${turn_metrics['cost']:<11.6f}"
        )


def print_repeat_summary(summary: Dict[str, Any]) -> None:
    metrics = summary["aggregate_total_metrics"]

    print()
    print("=" * 80)
    print("Repeated Experiment Summary")
    print("=" * 80)
    print()

    print(f"Run Count: {summary['run_count']}")
    print("Aggregate Total Metrics:")
    print(
        f"  Cache Hit Rate: {metrics['cache_hit_rate']['mean']:.1%} "
        f"+/- {metrics['cache_hit_rate']['std']:.1%}"
    )
    print(
        f"  Total Cost: ${metrics['cost']['mean']:.6f} "
        f"+/- ${metrics['cost']['std']:.6f}"
    )
    print(
        f"  Prompt Tokens: {metrics['prompt_tokens']['mean']:.1f} "
        f"(min {metrics['prompt_tokens']['min']}, max {metrics['prompt_tokens']['max']})"
    )
    print(
        f"  Cache Hit Tokens: {metrics['cache_hit_tokens']['mean']:.1f} "
        f"(min {metrics['cache_hit_tokens']['min']}, max {metrics['cache_hit_tokens']['max']})"
    )


def run_baseline_once(num_turns: int, run_id: int, seed: int) -> Dict[str, Any]:
    random.seed(seed)

    print("=" * 80)
    print(f"Baseline Experiment: Cache-Aware Agent (Run {run_id})")
    print("=" * 80)
    print()

    agent = create_baseline_agent()

    if run_id == 1:
        print("Session Config (Latched):")
        print(json.dumps(agent.session_config.to_dict(), indent=2))
        print()

        print("System Prompt Preview:")
        system_prompt = agent.prompt_manager.build_system_prompt()
        print(system_prompt[:500] + "...")
        print()

        print(f"Tool Cache: {len(agent.tool_cache)} tools registered")
        print()

    print(f"Running {num_turns} turns...")
    print("-" * 80)

    run_data = run_turn_sequence(agent, BASELINE_QUESTIONS[:num_turns], verbose=True, preview_chars=200)

    return {
        "experiment": "baseline",
        "schema_version": "v3",
        "run_id": run_id,
        "seed": seed,
        "num_turns": num_turns,
        "config": build_agent_config(
            agent,
            extra={
                **build_baseline_metadata(num_turns),
                "run_id": run_id,
                "seed": seed,
            },
        ),
        **run_data,
    }


def run_baseline_experiment(
    num_turns: int = 10,
    repeats: int = 1,
    seed: int = 42,
    output_dir: Path = DEFAULT_RESULTS_DIR,
) -> Dict[str, Any]:
    runs = [
        run_baseline_once(num_turns=num_turns, run_id=index + 1, seed=seed + index)
        for index in range(repeats)
    ]

    if repeats == 1:
        results = runs[0]
        print_run_summary(results)
    else:
        results = {
            "experiment": "baseline",
            "schema_version": "v3",
            "num_turns": num_turns,
            "repeat_count": repeats,
            "base_seed": seed,
            "config": build_baseline_metadata(num_turns),
            "summary": summarize_result_runs(runs),
            "runs": runs,
        }
        print_repeat_summary(results["summary"])

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = resolve_output_file(output_dir)
    output_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults saved to: {output_file}")
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the baseline cache-aware agent experiment.")
    parser.add_argument(
        "--turns",
        type=int,
        default=10,
        help="Number of turns to run in each baseline experiment.",
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
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_baseline_experiment(
        num_turns=args.turns,
        repeats=args.repeats,
        seed=args.seed,
        output_dir=Path(args.output_dir),
    )
