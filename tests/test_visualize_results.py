import unittest

from experiments.visualize_results import (
    build_tool_observability_sections,
    format_cost_with_std,
    format_percent_with_std,
)


class VisualizeResultsFormattingTests(unittest.TestCase):
    def test_format_percent_with_std_uses_ascii_separator(self):
        self.assertEqual(format_percent_with_std(0.5, 0.1), "50.00% +/- 10.00%")
        self.assertEqual(format_percent_with_std(0.5, 0.0), "50.00%")

    def test_format_cost_with_std_uses_ascii_separator(self):
        self.assertEqual(format_cost_with_std(1.2345, 0.2), "$1.2345 +/- $0.2000")
        self.assertEqual(format_cost_with_std(1.2345, 0.0), "$1.2345")

    def test_build_tool_observability_sections_surfaces_execution_enabled_track(self):
        sections = build_tool_observability_sections(
            baseline={"summary": {}},
            cache_busters={
                "tracks": {
                    "execution_enabled": {
                        "baseline": {
                            "summary": {
                                "aggregate_tool_observability": {
                                    "metrics": {
                                        "total_tool_executions": {"mean": 2.0, "std": 1.0},
                                        "tool_success_rate": {"mean": 0.75, "std": 0.25},
                                        "turns_terminated_by_max_rounds": {"mean": 0.5, "std": 0.5},
                                        "total_pending_tool_calls_after_loop": {"mean": 1.0, "std": 1.0},
                                    },
                                    "tool_name_counts": {"read_file": {"mean": 2.0, "std": 1.0}},
                                    "error_code_counts": {"path_not_allowed": {"mean": 0.5, "std": 0.5}},
                                    "pending_tool_name_counts": {"read_file": {"mean": 1.0, "std": 1.0}},
                                }
                            }
                        },
                        "scenarios": [],
                    }
                }
            },
        )

        joined = "\n".join(sections)
        self.assertIn("execution_enabled / Baseline", joined)
        self.assertIn("Tool executions: 2.00 +/- 1.00", joined)
        self.assertIn("`read_file` 2.00 +/- 1.00", joined)


if __name__ == "__main__":
    unittest.main()
