"""
Cache breaker experiments split into interpretable experiment tracks.

The core idea is to keep the execution logic generic while making tracks,
question sets, and breaker scenarios explicit data so later experiment
expansion does not require rewriting the runner itself.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Type

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent import CacheAwareAgent
from experiments.experiment_utils import (
    build_agent_config,
    run_turn_sequence,
    summarize_result_runs,
)


DEFAULT_RESULTS_DIR = Path("results")
COMBINED_FILENAME = "cache_busters_results.json"
SCHEMA_FILENAME = "cache_busters_schema_only.json"
EXECUTION_FILENAME = "cache_busters_execution_enabled.json"

SCHEMA_ONLY_QUESTIONS = [
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

EXECUTION_ENABLED_QUESTIONS = [
    "Use the read_file tool to inspect README.md and summarize the project goal.",
    "Use the read_file tool to inspect core/prompt_manager.py and explain the BOUNDARY design.",
    "Use the read_file tool to inspect core/message_manager.py and explain how append-only history is enforced.",
    "Use the read_file tool to inspect core/tool_cache.py and summarize the tool schema caching strategy.",
    "Use the read_file tool to inspect README.md and list the current tools status section.",
]


class BrokenAgent1_TimestampInStatic(CacheAwareAgent):
    """Inject a dynamic timestamp into the static prompt section."""

    def _initialize_dynamic_section(self) -> None:
        self.prompt_manager.add_static_section(f"Current timestamp: {time.time()}")
        super()._initialize_dynamic_section()


class BrokenAgent2_DynamicTools(CacheAwareAgent):
    """Change the exposed tool set between turns while keeping read_file available."""

    def _get_enabled_tool_schemas(self) -> List[Dict[str, Any]]:
        schemas = super()._get_enabled_tool_schemas()
        if random.random() > 0.5:
            return [schema for schema in schemas if schema["function"]["name"] != "echo_json"]
        return schemas


class BrokenAgent3_UnstableToolOrder(CacheAwareAgent):
    """Shuffle tool order on each request."""

    def _get_enabled_tool_schemas(self) -> List[Dict[str, Any]]:
        schemas = super()._get_enabled_tool_schemas()
        random.shuffle(schemas)
        return schemas


class BrokenAgent4_ModifyHistory(CacheAwareAgent):
    """Mutate the first historical user message after the first turn."""

    def _append_user_message(self, user_message: str) -> None:
        super()._append_user_message(user_message)
        if len(self.message_manager) > 1:
            self.message_manager._messages[0].content += f" [Modified at {time.time()}]"


class BrokenAgent5_NonDeterministicSerialization(CacheAwareAgent):
    """Rebuild tool schemas with randomly ordered keys on each request."""

    def _shuffle_structure(self, value: Any) -> Any:
        if isinstance(value, dict):
            items = list(value.items())
            random.shuffle(items)
            return {key: self._shuffle_structure(item_value) for key, item_value in items}
        if isinstance(value, list):
            return [self._shuffle_structure(item) for item in value]
        return value

    def _get_enabled_tool_schemas(self) -> List[Dict[str, Any]]:
        schemas = super()._get_enabled_tool_schemas()
        return [self._shuffle_structure(schema) for schema in schemas]


class BrokenAgent6_ModelSwitch(CacheAwareAgent):
    """Switch models between requests inside the same session."""

    def _create_completion(self, messages: List[Dict[str, Any]]) -> Any:
        self.session_config.model = random.choice(["deepseek-chat", "deepseek-reasoner"])
        return super()._create_completion(messages)


@dataclass(frozen=True)
class ScenarioSpec:
    """A single cache-breaker scenario definition."""

    key: str
    title: str
    description: str
    agent_class: Type[CacheAwareAgent]
    category: str


@dataclass(frozen=True)
class TrackSpec:
    """A runnable experiment track definition."""

    key: str
    title: str
    description: str
    questions: List[str]
    agent_kwargs: Dict[str, Any]
    baseline_dynamic_section: str
    scenarios: List[ScenarioSpec]
    output_filename: str


SCENARIOS = {
    "timestamp_static": ScenarioSpec(
        key="timestamp_static",
        title="1. Timestamp in Static Section",
        description="Inject a dynamic timestamp into the static system prompt section.",
        agent_class=BrokenAgent1_TimestampInStatic,
        category="prompt_static",
    ),
    "dynamic_tools": ScenarioSpec(
        key="dynamic_tools",
        title="2. Dynamic Tool Add/Remove",
        description="Change the exposed tool set between turns.",
        agent_class=BrokenAgent2_DynamicTools,
        category="tool_schema",
    ),
    "unstable_tool_order": ScenarioSpec(
        key="unstable_tool_order",
        title="3. Unstable Tool Order",
        description="Shuffle enabled tool order on each request.",
        agent_class=BrokenAgent3_UnstableToolOrder,
        category="tool_schema",
    ),
    "modify_history": ScenarioSpec(
        key="modify_history",
        title="4. Modify Message History",
        description="Mutate historical user content after the first turn.",
        agent_class=BrokenAgent4_ModifyHistory,
        category="message_history",
    ),
    "nondeterministic_serialization": ScenarioSpec(
        key="nondeterministic_serialization",
        title="5. Non-Deterministic Serialization",
        description="Emit equivalent tool schemas with unstable key ordering.",
        agent_class=BrokenAgent5_NonDeterministicSerialization,
        category="tool_schema",
    ),
    "model_switch": ScenarioSpec(
        key="model_switch",
        title="6. Model Switch Mid-Session",
        description="Switch completion models inside the same logical session.",
        agent_class=BrokenAgent6_ModelSwitch,
        category="session_config",
    ),
}

TRACKS = {
    "schema_only": TrackSpec(
        key="schema_only",
        title="Schema-Only Track",
        description="Focus on prompt/message/session stability without active tool execution.",
        questions=SCHEMA_ONLY_QUESTIONS,
        agent_kwargs={
            "enable_tools": False,
            "temperature": 0.7,
        },
        baseline_dynamic_section="Track mode: schema-only. Answer directly without using tools.",
        scenarios=[
            SCENARIOS["timestamp_static"],
            SCENARIOS["modify_history"],
            SCENARIOS["model_switch"],
        ],
        output_filename=SCHEMA_FILENAME,
    ),
    "execution_enabled": TrackSpec(
        key="execution_enabled",
        title="Execution-Enabled Track",
        description="Evaluate breaker effects when the minimal tool loop is active.",
        questions=EXECUTION_ENABLED_QUESTIONS,
        agent_kwargs={
            "enable_tools": True,
            "max_tool_rounds": 1,
            "temperature": 0.0,
        },
        baseline_dynamic_section="Track mode: execution-enabled. Use tools when the user explicitly asks for file inspection.",
        scenarios=[
            SCENARIOS["dynamic_tools"],
            SCENARIOS["unstable_tool_order"],
            SCENARIOS["nondeterministic_serialization"],
        ],
        output_filename=EXECUTION_FILENAME,
    ),
}


def resolve_output_file(output_dir: Path, filename: str) -> Path:
    return output_dir / filename


def create_agent(agent_class: Type[CacheAwareAgent], track: TrackSpec) -> CacheAwareAgent:
    agent = agent_class(
        model="deepseek-chat",
        max_tokens=1024,
        **track.agent_kwargs,
    )
    agent.prompt_manager.add_dynamic_section(track.baseline_dynamic_section)
    return agent


def build_track_metadata(track: TrackSpec, num_turns: int) -> Dict[str, Any]:
    return {
        "description": track.description,
        "agent_kwargs": track.agent_kwargs,
        "baseline_dynamic_section": track.baseline_dynamic_section,
        "questions": track.questions[:num_turns],
        "scenario_keys": [scenario.key for scenario in track.scenarios],
        "scenario_titles": [scenario.title for scenario in track.scenarios],
    }


def run_track_baseline(track: TrackSpec, num_turns: int, run_id: int, seed: int) -> Dict[str, Any]:
    agent = create_agent(CacheAwareAgent, track)

    print(f"\n{'=' * 80}")
    print(f"Baseline: {track.title}")
    print(f"{'=' * 80}\n")

    run_data = run_turn_sequence(agent, track.questions[:num_turns], verbose=True)
    return {
        "scenario": "Baseline",
        "scenario_key": "baseline",
        "scenario_description": f"Baseline run for {track.title}.",
        "run_id": run_id,
        "seed": seed,
        "config": build_agent_config(
            agent,
            extra={
                "track": track.key,
                "questions": track.questions[:num_turns],
                "mode": "baseline",
                "run_id": run_id,
                "seed": seed,
            },
        ),
        **run_data,
    }


def run_cache_buster_experiment(
    track: TrackSpec,
    scenario: ScenarioSpec,
    num_turns: int,
    run_id: int,
    seed: int,
) -> Dict[str, Any]:
    print(f"\n{'=' * 80}")
    print(f"{track.title} | Scenario: {scenario.title}")
    print(f"{'=' * 80}\n")

    agent = create_agent(scenario.agent_class, track)
    run_data = run_turn_sequence(agent, track.questions[:num_turns], verbose=True)
    total_metrics = run_data["total_metrics"]

    print(f"\nResults for {scenario.title}:")
    print(f"  Cache Hit Rate: {total_metrics['cache_hit_rate']:.1%}")
    print(f"  Total Cost: ${total_metrics['cost']:.6f}")

    return {
        "scenario": scenario.title,
        "scenario_key": scenario.key,
        "scenario_description": scenario.description,
        "scenario_category": scenario.category,
        "run_id": run_id,
        "seed": seed,
        "config": build_agent_config(
            agent,
            extra={
                "track": track.key,
                "questions": track.questions[:num_turns],
                "mode": "scenario",
                "scenario": scenario.title,
                "scenario_key": scenario.key,
                "scenario_category": scenario.category,
                "agent_class": scenario.agent_class.__name__,
                "run_id": run_id,
                "seed": seed,
            },
        ),
        **run_data,
    }


def run_track_once(track_key: str, num_turns: int, run_id: int, seed: int) -> Dict[str, Any]:
    track = TRACKS[track_key]
    random.seed(seed)

    baseline = run_track_baseline(track, num_turns, run_id, seed)
    scenarios = [
        run_cache_buster_experiment(track, scenario, num_turns, run_id, seed)
        for scenario in track.scenarios
    ]

    return {
        "track": track.key,
        "title": track.title,
        "schema_version": "v3",
        "run_id": run_id,
        "seed": seed,
        "num_turns": num_turns,
        "config": build_track_metadata(track, num_turns),
        "baseline": baseline,
        "scenarios": scenarios,
    }


def run_track(
    track_key: str,
    num_turns: int,
    repeats: int = 1,
    seed: int = 42,
    output_dir: Path = DEFAULT_RESULTS_DIR,
) -> Dict[str, Any]:
    track = TRACKS[track_key]
    runs = [
        run_track_once(track_key, num_turns, run_id=index + 1, seed=seed + index)
        for index in range(repeats)
    ]

    if repeats == 1:
        track_results = runs[0]
    else:
        baseline_runs = [run["baseline"] for run in runs]
        scenario_runs_by_key = {
            scenario.key: [run["scenarios"][index] for run in runs]
            for index, scenario in enumerate(track.scenarios)
        }

        track_results = {
            "track": track.key,
            "title": track.title,
            "schema_version": "v3",
            "num_turns": num_turns,
            "repeat_count": repeats,
            "base_seed": seed,
            "config": build_track_metadata(track, num_turns),
            "baseline": {
                "scenario": "Baseline",
                "scenario_key": "baseline",
                "summary": summarize_result_runs(baseline_runs),
                "runs": baseline_runs,
            },
            "scenarios": [
                {
                    "scenario": scenario.title,
                    "scenario_key": scenario.key,
                    "scenario_description": scenario.description,
                    "scenario_category": scenario.category,
                    "summary": summarize_result_runs(scenario_runs_by_key[scenario.key]),
                    "runs": scenario_runs_by_key[scenario.key],
                }
                for scenario in track.scenarios
            ],
            "runs": runs,
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = resolve_output_file(output_dir, track.output_filename)
    output_file.write_text(
        json.dumps(track_results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return track_results


def run_all_cache_busters(
    num_turns: int = 5,
    repeats: int = 1,
    seed: int = 42,
    output_dir: Path = DEFAULT_RESULTS_DIR,
) -> Dict[str, Any]:
    print("=" * 80)
    print("Cache Busters Experiment: Split Tracks")
    print("=" * 80)

    schema_only = run_track("schema_only", num_turns, repeats=repeats, seed=seed, output_dir=output_dir)
    execution_enabled = run_track(
        "execution_enabled",
        num_turns,
        repeats=repeats,
        seed=seed,
        output_dir=output_dir,
    )

    combined = {
        "experiment": "cache_busters",
        "schema_version": "v3",
        "repeat_count": repeats,
        "base_seed": seed,
        "tracks": {
            "schema_only": schema_only,
            "execution_enabled": execution_enabled,
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    combined_output = resolve_output_file(output_dir, COMBINED_FILENAME)
    schema_output = resolve_output_file(output_dir, SCHEMA_FILENAME)
    execution_output = resolve_output_file(output_dir, EXECUTION_FILENAME)
    combined_output.write_text(
        json.dumps(combined, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nResults saved to: {combined_output}")
    print(f"Schema-only track saved to: {schema_output}")
    print(f"Execution-enabled track saved to: {execution_output}")
    return combined


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run cache breaker experiments in schema-only or execution-enabled mode."
    )
    parser.add_argument(
        "--track",
        choices=["all", *TRACKS.keys()],
        default="all",
        help="Which experiment track to run.",
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=5,
        help="Number of turns to run per track.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for repeatable scenario behavior.",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="How many repeated runs to execute per track.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print available tracks and scenarios without running experiments.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_RESULTS_DIR),
        help="Directory where result artifacts should be written.",
    )
    return parser.parse_args()


def print_available_configs() -> None:
    print("Available experiment tracks:")
    for track in TRACKS.values():
        print(f"- {track.key}: {track.title}")
        print(f"  {track.description}")
        for scenario in track.scenarios:
            print(f"  - {scenario.key}: {scenario.title} [{scenario.category}]")


if __name__ == "__main__":
    args = parse_args()

    if args.list:
        print_available_configs()
    elif args.track == "all":
        run_all_cache_busters(
            num_turns=args.turns,
            repeats=args.repeats,
            seed=args.seed,
            output_dir=Path(args.output_dir),
        )
    else:
        result = run_track(
            args.track,
            args.turns,
            repeats=args.repeats,
            seed=args.seed,
            output_dir=Path(args.output_dir),
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
