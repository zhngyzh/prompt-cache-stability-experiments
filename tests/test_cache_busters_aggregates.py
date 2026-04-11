import unittest

from experiments.experiment_utils import (
    aggregate_metric_dicts,
    summarize_result_runs,
    summarize_turn_traces,
)


class CacheBusterAggregateTests(unittest.TestCase):
    def test_aggregate_metric_dicts_computes_mean_std_min_max(self):
        aggregated = aggregate_metric_dicts(
            [
                {"cache_hit_rate": 0.5, "cost": 1.0},
                {"cache_hit_rate": 0.7, "cost": 3.0},
            ]
        )

        self.assertAlmostEqual(aggregated["cache_hit_rate"]["mean"], 0.6)
        self.assertAlmostEqual(aggregated["cache_hit_rate"]["std"], 0.1)
        self.assertEqual(aggregated["cache_hit_rate"]["min"], 0.5)
        self.assertEqual(aggregated["cache_hit_rate"]["max"], 0.7)
        self.assertAlmostEqual(aggregated["cost"]["mean"], 2.0)

    def test_summarize_result_runs_uses_total_metrics(self):
        summary = summarize_result_runs(
            [
                {"total_metrics": {"cache_hit_rate": 0.5, "cost": 1.0}},
                {"total_metrics": {"cache_hit_rate": 0.7, "cost": 3.0}},
            ]
        )

        self.assertEqual(summary["run_count"], 2)
        self.assertAlmostEqual(summary["aggregate_total_metrics"]["cache_hit_rate"]["mean"], 0.6)
        self.assertAlmostEqual(summary["aggregate_total_metrics"]["cost"]["max"], 3.0)

    def test_summarize_result_runs_aggregates_per_turn_metrics(self):
        summary = summarize_result_runs(
            [
                {
                    "total_metrics": {"cache_hit_rate": 0.5, "cost": 1.0},
                    "per_turn_metrics": [
                        {"turn": 1, "cache_hit_rate": 0.2, "cost": 0.4},
                        {"turn": 2, "cache_hit_rate": 0.8, "cost": 0.6},
                    ],
                },
                {
                    "total_metrics": {"cache_hit_rate": 0.7, "cost": 3.0},
                    "per_turn_metrics": [
                        {"turn": 1, "cache_hit_rate": 0.4, "cost": 0.5},
                        {"turn": 2, "cache_hit_rate": 0.6, "cost": 0.7},
                    ],
                },
            ]
        )

        self.assertEqual(len(summary["aggregate_per_turn_metrics"]), 2)
        self.assertEqual(summary["aggregate_per_turn_metrics"][0]["turn"], 1)
        self.assertAlmostEqual(
            summary["aggregate_per_turn_metrics"][0]["cache_hit_rate"]["mean"], 0.3
        )
        self.assertAlmostEqual(summary["aggregate_per_turn_metrics"][1]["cost"]["mean"], 0.65)

    def test_summarize_turn_traces_builds_tool_observability_metrics(self):
        observability = summarize_turn_traces(
            [
                {
                    "turn": 1,
                    "trace": {
                        "tool_call_count": 1,
                        "tool_execution_count": 1,
                        "tool_rounds_executed": 1,
                        "completion_round_count": 2,
                        "pending_tool_calls_after_loop": 0,
                        "pending_tool_names_after_loop": [],
                        "tool_loop_terminated_by_max_rounds": False,
                        "tool_execution_results": [
                            {
                                "tool_name": "read_file",
                                "success": True,
                                "status": "ok",
                            }
                        ],
                    },
                },
                {
                    "turn": 2,
                    "trace": {
                        "tool_call_count": 1,
                        "tool_execution_count": 1,
                        "tool_rounds_executed": 1,
                        "completion_round_count": 2,
                        "pending_tool_calls_after_loop": 1,
                        "pending_tool_names_after_loop": ["echo_json"],
                        "tool_loop_terminated_by_max_rounds": True,
                        "tool_execution_results": [
                            {
                                "tool_name": "read_file",
                                "success": False,
                                "status": "error",
                                "error": {"code": "path_not_allowed"},
                            }
                        ],
                    },
                },
            ]
        )

        self.assertEqual(observability["metrics"]["turn_count"], 2)
        self.assertEqual(observability["metrics"]["total_tool_executions"], 2)
        self.assertEqual(observability["metrics"]["failed_tool_executions"], 1)
        self.assertAlmostEqual(observability["metrics"]["tool_success_rate"], 0.5)
        self.assertEqual(observability["metrics"]["turns_terminated_by_max_rounds"], 1)
        self.assertEqual(observability["tool_name_counts"]["read_file"], 2)
        self.assertEqual(observability["error_code_counts"]["path_not_allowed"], 1)
        self.assertEqual(observability["pending_tool_name_counts"]["echo_json"], 1)

    def test_summarize_result_runs_aggregates_tool_observability(self):
        summary = summarize_result_runs(
            [
                {
                    "total_metrics": {"cache_hit_rate": 0.5, "cost": 1.0},
                    "tool_observability": {
                        "metrics": {
                            "total_tool_executions": 1,
                            "tool_success_rate": 1.0,
                            "turns_terminated_by_max_rounds": 0,
                            "total_pending_tool_calls_after_loop": 0,
                        },
                        "tool_name_counts": {"read_file": 1},
                        "error_code_counts": {},
                        "pending_tool_name_counts": {},
                    },
                },
                {
                    "total_metrics": {"cache_hit_rate": 0.7, "cost": 3.0},
                    "tool_observability": {
                        "metrics": {
                            "total_tool_executions": 3,
                            "tool_success_rate": 2 / 3,
                            "turns_terminated_by_max_rounds": 1,
                            "total_pending_tool_calls_after_loop": 2,
                        },
                        "tool_name_counts": {"read_file": 2, "echo_json": 1},
                        "error_code_counts": {"path_not_allowed": 1},
                        "pending_tool_name_counts": {"echo_json": 2},
                    },
                },
            ]
        )

        aggregate_tool = summary["aggregate_tool_observability"]
        self.assertAlmostEqual(aggregate_tool["metrics"]["total_tool_executions"]["mean"], 2.0)
        self.assertAlmostEqual(aggregate_tool["metrics"]["tool_success_rate"]["mean"], 5 / 6)
        self.assertAlmostEqual(aggregate_tool["tool_name_counts"]["read_file"]["mean"], 1.5)
        self.assertAlmostEqual(aggregate_tool["error_code_counts"]["path_not_allowed"]["max"], 1)
        self.assertAlmostEqual(aggregate_tool["pending_tool_name_counts"]["echo_json"]["mean"], 1.0)


if __name__ == "__main__":
    unittest.main()
