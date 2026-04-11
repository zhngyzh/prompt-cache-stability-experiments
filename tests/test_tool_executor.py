import json
import tempfile
import unittest
from pathlib import Path

from core.tool_executor import ToolExecutionResult, create_default_tool_executor


class ToolExecutorTests(unittest.TestCase):
    def test_default_executor_supports_minimal_deterministic_tools(self):
        executor = create_default_tool_executor()

        self.assertTrue(executor.supports("echo_json"))
        self.assertTrue(executor.supports("read_file"))
        self.assertFalse(executor.supports("write_file"))

    def test_unsupported_tool_returns_structured_error(self):
        executor = create_default_tool_executor()

        result = executor.execute("missing_tool", {})

        self.assertFalse(result.success)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "unsupported_tool")
        self.assertIn("Unsupported tool", result.error["message"])
        self.assertIsNone(result.output)

    def test_read_file_returns_workspace_relative_path_and_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            file_path = workspace_root / "notes.txt"
            file_path.write_text("hello workspace", encoding="utf-8")

            executor = create_default_tool_executor(workspace_root=workspace_root)
            result = executor.execute("read_file", {"file_path": "notes.txt"})

        self.assertTrue(result.success)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["workspace_relative_path"], "notes.txt")
        self.assertEqual(result.output["content"], "hello workspace")

    def test_read_file_blocks_access_outside_workspace(self):
        with tempfile.TemporaryDirectory() as workspace_dir, tempfile.TemporaryDirectory() as outside_dir:
            outside_file = Path(outside_dir) / "secret.txt"
            outside_file.write_text("should not leak", encoding="utf-8")

            executor = create_default_tool_executor(workspace_root=workspace_dir)
            result = executor.execute("read_file", {"file_path": str(outside_file)})

        self.assertFalse(result.success)
        self.assertEqual(result.error["code"], "path_not_allowed")
        self.assertIn("workspace_root", result.error["details"])

    def test_invalid_argument_returns_structured_error(self):
        executor = create_default_tool_executor()

        result = executor.execute("echo_json", {"text": ""})

        self.assertFalse(result.success)
        self.assertEqual(result.error["code"], "invalid_arguments")
        self.assertEqual(result.error["details"]["argument"], "text")

    def test_tool_execution_result_serializes_deterministically(self):
        result = ToolExecutionResult.ok(
            name="read_file",
            output={"b": 2, "a": 1},
        )

        serialized = result.to_message_content()
        parsed = json.loads(serialized)

        self.assertEqual(parsed["tool"], "read_file")
        self.assertEqual(parsed["status"], "ok")
        self.assertTrue(parsed["success"])
        self.assertIsNone(parsed["error"])
        self.assertEqual(list(parsed["output"].keys()), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
