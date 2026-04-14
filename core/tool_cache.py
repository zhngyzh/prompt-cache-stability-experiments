"""
Tool schema caching utilities.

The cache stores deterministically serialized tool schemas so the request prefix
stays stable across turns and across repeated experiment runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class BaseTool:
    """Minimal tool schema representation."""

    name: str
    description: str
    parameters: Dict[str, Any]

    def to_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolSchemaCache:
    """
    Deterministic tool schema cache.

    Tool definitions are serialized with `sort_keys=True` and returned in sorted
    name order so tool-related prompt prefixes remain stable.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, str] = {}
        self._tools: Dict[str, BaseTool] = {}

    def register_tool(self, tool: BaseTool) -> None:
        if tool.name in self._cache:
            return

        schema = tool.to_schema()
        serialized = json.dumps(schema, sort_keys=True, ensure_ascii=False)
        self._cache[tool.name] = serialized
        self._tools[tool.name] = tool

    def get_tool_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        if tool_name not in self._cache:
            return None
        return json.loads(self._cache[tool_name])

    def get_all_schemas(self) -> List[Dict[str, Any]]:
        sorted_names = sorted(self._cache.keys())
        return [json.loads(self._cache[name]) for name in sorted_names]

    def get_all_schemas_json(self) -> str:
        return json.dumps(self.get_all_schemas(), sort_keys=True, ensure_ascii=False)

    def clear(self) -> None:
        self._cache.clear()
        self._tools.clear()

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, tool_name: str) -> bool:
        return tool_name in self._cache

    def __repr__(self) -> str:
        return f"ToolSchemaCache(tools={len(self._cache)})"


def create_read_file_tool() -> BaseTool:
    return BaseTool(
        name="read_file",
        description="Read the contents of a UTF-8 text file",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to read",
                }
            },
            "required": ["file_path"],
        },
    )


def create_write_file_tool() -> BaseTool:
    return BaseTool(
        name="write_file",
        description="Write content to a file",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write",
                },
            },
            "required": ["file_path", "content"],
        },
    )


def create_python_execute_tool() -> BaseTool:
    return BaseTool(
        name="python_execute",
        description="Execute Python code and return the result",
        parameters={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute",
                }
            },
            "required": ["code"],
        },
    )


def create_echo_json_tool() -> BaseTool:
    return BaseTool(
        name="echo_json",
        description="Return the provided text in a deterministic JSON payload",
        parameters={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to echo back",
                }
            },
            "required": ["text"],
        },
    )


def create_list_directory_tool() -> BaseTool:
    return BaseTool(
        name="list_directory",
        description="List the contents of a directory within the workspace",
        parameters={
            "type": "object",
            "properties": {
                "dir_path": {
                    "type": "string",
                    "description": "Path to the directory to list",
                }
            },
            "required": ["dir_path"],
        },
    )


def create_search_content_tool() -> BaseTool:
    return BaseTool(
        name="search_content",
        description="Search for a keyword in a text file and return matching lines",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to search",
                },
                "keyword": {
                    "type": "string",
                    "description": "Keyword to search for",
                },
            },
            "required": ["file_path", "keyword"],
        },
    )


def create_default_tool_cache() -> ToolSchemaCache:
    cache = ToolSchemaCache()
    cache.register_tool(create_echo_json_tool())
    cache.register_tool(create_list_directory_tool())
    cache.register_tool(create_read_file_tool())
    cache.register_tool(create_search_content_tool())
    cache.register_tool(create_write_file_tool())
    cache.register_tool(create_python_execute_tool())
    return cache
