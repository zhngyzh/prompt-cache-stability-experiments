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
        self.assertTrue(executor.supports("write_file"))
        self.assertTrue(executor.supports("list_directory"))
        self.assertTrue(executor.supports("search_content"))

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

    def test_write_file_creates_file_with_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            executor = create_default_tool_executor(workspace_root=workspace_root)

            result = executor.execute("write_file", {
                "file_path": "output.txt",
                "content": "test content"
            })

            self.assertTrue(result.success)
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.output["workspace_relative_path"], "output.txt")
            self.assertGreater(result.output["bytes_written"], 0)

            written_file = workspace_root / "output.txt"
            self.assertTrue(written_file.exists())
            self.assertEqual(written_file.read_text(encoding="utf-8"), "test content")

    def test_write_file_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            executor = create_default_tool_executor(workspace_root=workspace_root)

            result = executor.execute("write_file", {
                "file_path": "subdir/nested/file.txt",
                "content": "nested content"
            })

            self.assertTrue(result.success)
            written_file = workspace_root / "subdir" / "nested" / "file.txt"
            self.assertTrue(written_file.exists())
            self.assertEqual(written_file.read_text(encoding="utf-8"), "nested content")

    def test_write_file_blocks_access_outside_workspace(self):
        with tempfile.TemporaryDirectory() as workspace_dir, tempfile.TemporaryDirectory() as outside_dir:
            outside_file = Path(outside_dir) / "outside.txt"

            executor = create_default_tool_executor(workspace_root=workspace_dir)
            result = executor.execute("write_file", {
                "file_path": str(outside_file),
                "content": "should not write"
            })

        self.assertFalse(result.success)
        self.assertEqual(result.error["code"], "path_not_allowed")
        self.assertFalse(outside_file.exists())

    def test_list_directory_returns_sorted_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            (workspace_root / "file_b.txt").write_text("b", encoding="utf-8")
            (workspace_root / "file_a.txt").write_text("a", encoding="utf-8")
            (workspace_root / "dir_z").mkdir()
            (workspace_root / "dir_y").mkdir()

            executor = create_default_tool_executor(workspace_root=workspace_root)
            result = executor.execute("list_directory", {"dir_path": "."})

        self.assertTrue(result.success)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["count"], 4)

        entries = result.output["entries"]
        names = [e["name"] for e in entries]
        self.assertEqual(names, ["dir_y", "dir_z", "file_a.txt", "file_b.txt"])

        # Check types
        self.assertEqual(entries[0]["type"], "directory")
        self.assertEqual(entries[2]["type"], "file")
        self.assertIn("size", entries[2])
        self.assertNotIn("size", entries[0])

    def test_list_directory_blocks_access_outside_workspace(self):
        with tempfile.TemporaryDirectory() as workspace_dir, tempfile.TemporaryDirectory() as outside_dir:
            executor = create_default_tool_executor(workspace_root=workspace_dir)
            result = executor.execute("list_directory", {"dir_path": outside_dir})

        self.assertFalse(result.success)
        self.assertEqual(result.error["code"], "path_not_allowed")

    def test_list_directory_returns_error_for_nonexistent_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            executor = create_default_tool_executor(workspace_root=temp_dir)
            result = executor.execute("list_directory", {"dir_path": "nonexistent"})

        self.assertFalse(result.success)
        self.assertEqual(result.error["code"], "directory_not_found")

    def test_search_content_finds_matching_lines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            test_file = workspace_root / "test.txt"
            test_file.write_text("line 1: hello\nline 2: world\nline 3: hello again", encoding="utf-8")

            executor = create_default_tool_executor(workspace_root=workspace_root)
            result = executor.execute("search_content", {
                "file_path": "test.txt",
                "keyword": "hello"
            })

        self.assertTrue(result.success)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["keyword"], "hello")
        self.assertEqual(result.output["match_count"], 2)

        matches = result.output["matches"]
        self.assertEqual(matches[0]["line_number"], 1)
        self.assertEqual(matches[0]["line_content"], "line 1: hello")
        self.assertEqual(matches[1]["line_number"], 3)
        self.assertEqual(matches[1]["line_content"], "line 3: hello again")

    def test_search_content_returns_empty_for_no_matches(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            test_file = workspace_root / "test.txt"
            test_file.write_text("no matches here", encoding="utf-8")

            executor = create_default_tool_executor(workspace_root=workspace_root)
            result = executor.execute("search_content", {
                "file_path": "test.txt",
                "keyword": "missing"
            })

        self.assertTrue(result.success)
        self.assertEqual(result.output["match_count"], 0)
        self.assertEqual(result.output["matches"], [])

    def test_search_content_blocks_access_outside_workspace(self):
        with tempfile.TemporaryDirectory() as workspace_dir, tempfile.TemporaryDirectory() as outside_dir:
            outside_file = Path(outside_dir) / "outside.txt"
            outside_file.write_text("secret", encoding="utf-8")

            executor = create_default_tool_executor(workspace_root=workspace_dir)
            result = executor.execute("search_content", {
                "file_path": str(outside_file),
                "keyword": "secret"
            })

        self.assertFalse(result.success)
        self.assertEqual(result.error["code"], "path_not_allowed")


if __name__ == "__main__":
    unittest.main()
