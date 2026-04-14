"""
Local tool execution layer.

This module keeps tool execution separate from tool schema generation so the
agent can evolve from "schema only" to a real tool-calling loop incrementally.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict


ToolHandler = Callable[[dict[str, Any], "LocalToolExecutor"], dict[str, Any]]


@dataclass
class ToolExecutionError(Exception):
    """Structured tool execution error."""

    code: str
    message: str
    details: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload

    def __str__(self) -> str:
        return self.message


@dataclass
class ToolExecutionResult:
    """Normalized tool execution result."""

    name: str
    success: bool
    status: str
    output: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    @classmethod
    def ok(cls, name: str, output: dict[str, Any]) -> "ToolExecutionResult":
        return cls(name=name, success=True, status="ok", output=output, error=None)

    @classmethod
    def failure(
        cls,
        name: str,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> "ToolExecutionResult":
        return cls(
            name=name,
            success=False,
            status="error",
            output=None,
            error=ToolExecutionError(code=code, message=message, details=details).to_payload(),
        )

    def to_message_content(self) -> str:
        """Serialize output deterministically for stable tool messages."""
        payload = {
            "tool": self.name,
            "status": self.status,
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


class LocalToolExecutor:
    """Simple registry-based local tool executor."""

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self._handlers: Dict[str, ToolHandler] = {}
        self.workspace_root = Path(workspace_root or Path.cwd()).expanduser().resolve()

    def register(self, name: str, handler: ToolHandler) -> None:
        self._handlers[name] = handler

    def supports(self, name: str) -> bool:
        return name in self._handlers

    def resolve_workspace_path(self, file_path: str) -> Path:
        path = Path(file_path).expanduser()
        if not path.is_absolute():
            path = self.workspace_root / path
        return path.resolve()

    def ensure_within_workspace(self, path: Path) -> None:
        if not path.is_relative_to(self.workspace_root):
            raise ToolExecutionError(
                code="path_not_allowed",
                message="Access denied outside workspace root.",
                details={
                    "requested_path": str(path),
                    "workspace_root": str(self.workspace_root),
                },
            )

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        if name not in self._handlers:
            return ToolExecutionResult.failure(
                name=name,
                code="unsupported_tool",
                message=f"Unsupported tool: {name}",
            )

        try:
            output = self._handlers[name](arguments, self)
            return ToolExecutionResult.ok(name=name, output=output)
        except ToolExecutionError as exc:
            return ToolExecutionResult(
                name=name,
                success=False,
                status="error",
                output=None,
                error=exc.to_payload(),
            )
        except Exception as exc:  # noqa: BLE001
            return ToolExecutionResult.failure(
                name=name,
                code="tool_execution_failed",
                message=str(exc),
            )


def _require_string_argument(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ToolExecutionError(
            code="invalid_arguments",
            message=f"Expected a non-empty string argument: {key}",
            details={"argument": key},
        )
    return value


def _read_file_handler(arguments: dict[str, Any], executor: LocalToolExecutor) -> dict[str, Any]:
    file_path = _require_string_argument(arguments, "file_path")
    path = executor.resolve_workspace_path(file_path)
    executor.ensure_within_workspace(path)

    if not path.exists():
        raise ToolExecutionError(
            code="file_not_found",
            message="Requested file does not exist.",
            details={"requested_path": str(path)},
        )

    if not path.is_file():
        raise ToolExecutionError(
            code="not_a_file",
            message="Requested path is not a file.",
            details={"requested_path": str(path)},
        )

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolExecutionError(
            code="decode_error",
            message="Requested file is not valid UTF-8 text.",
            details={"requested_path": str(path), "reason": str(exc)},
        ) from exc

    return {
        "file_path": str(path),
        "workspace_relative_path": path.relative_to(executor.workspace_root).as_posix(),
        "content": content,
    }


def _echo_json_handler(arguments: dict[str, Any], executor: LocalToolExecutor) -> dict[str, Any]:
    del executor
    return {"text": _require_string_argument(arguments, "text")}


def _list_directory_handler(arguments: dict[str, Any], executor: LocalToolExecutor) -> dict[str, Any]:
    dir_path = _require_string_argument(arguments, "dir_path")
    path = executor.resolve_workspace_path(dir_path)
    executor.ensure_within_workspace(path)

    if not path.exists():
        raise ToolExecutionError(
            code="directory_not_found",
            message="Requested directory does not exist.",
            details={"requested_path": str(path)},
        )

    if not path.is_dir():
        raise ToolExecutionError(
            code="not_a_directory",
            message="Requested path is not a directory.",
            details={"requested_path": str(path)},
        )

    try:
        entries = []
        for item in sorted(path.iterdir()):
            entry = {
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "path": item.relative_to(executor.workspace_root).as_posix(),
            }
            if item.is_file():
                entry["size"] = item.stat().st_size
            entries.append(entry)

        return {
            "dir_path": str(path),
            "workspace_relative_path": path.relative_to(executor.workspace_root).as_posix(),
            "entries": entries,
            "count": len(entries),
        }
    except PermissionError as exc:
        raise ToolExecutionError(
            code="permission_denied",
            message="Permission denied when accessing directory.",
            details={"requested_path": str(path), "reason": str(exc)},
        ) from exc


def _write_file_handler(arguments: dict[str, Any], executor: LocalToolExecutor) -> dict[str, Any]:
    file_path = _require_string_argument(arguments, "file_path")
    content = _require_string_argument(arguments, "content")

    path = executor.resolve_workspace_path(file_path)
    executor.ensure_within_workspace(path)

    # Create parent directories if they don't exist
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        path.write_text(content, encoding="utf-8")
    except Exception as exc:
        raise ToolExecutionError(
            code="write_failed",
            message="Failed to write file.",
            details={"requested_path": str(path), "reason": str(exc)},
        ) from exc

    return {
        "file_path": str(path),
        "workspace_relative_path": path.relative_to(executor.workspace_root).as_posix(),
        "bytes_written": len(content.encode("utf-8")),
    }


def _search_content_handler(arguments: dict[str, Any], executor: LocalToolExecutor) -> dict[str, Any]:
    file_path = _require_string_argument(arguments, "file_path")
    keyword = _require_string_argument(arguments, "keyword")

    path = executor.resolve_workspace_path(file_path)
    executor.ensure_within_workspace(path)

    if not path.exists():
        raise ToolExecutionError(
            code="file_not_found",
            message="Requested file does not exist.",
            details={"requested_path": str(path)},
        )

    if not path.is_file():
        raise ToolExecutionError(
            code="not_a_file",
            message="Requested path is not a file.",
            details={"requested_path": str(path)},
        )

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolExecutionError(
            code="decode_error",
            message="Requested file is not valid UTF-8 text.",
            details={"requested_path": str(path), "reason": str(exc)},
        ) from exc

    lines = content.splitlines()
    matches = []
    for line_num, line in enumerate(lines, start=1):
        if keyword in line:
            matches.append({
                "line_number": line_num,
                "line_content": line,
            })

    return {
        "file_path": str(path),
        "workspace_relative_path": path.relative_to(executor.workspace_root).as_posix(),
        "keyword": keyword,
        "matches": matches,
        "match_count": len(matches),
    }


def create_default_tool_executor(workspace_root: str | Path | None = None) -> LocalToolExecutor:
    """
    Create the deterministic tool set for the first tool-calling phase.

    We intentionally keep the set small and deterministic so execution-enabled
    cache experiments remain easy to reason about.
    """

    executor = LocalToolExecutor(workspace_root=workspace_root)
    executor.register("echo_json", _echo_json_handler)
    executor.register("list_directory", _list_directory_handler)
    executor.register("read_file", _read_file_handler)
    executor.register("search_content", _search_content_handler)
    executor.register("write_file", _write_file_handler)
    return executor
