import unittest
from types import SimpleNamespace

from core.agent import CacheAwareAgent


class FakeToolCall:
    def __init__(self, tool_id: str, name: str, arguments: str):
        self.id = tool_id
        self.function = SimpleNamespace(name=name, arguments=arguments)

    def model_dump(self):
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.function.name,
                "arguments": self.function.arguments,
            },
        }


class FakeResponse:
    def __init__(self, message, prompt_tokens: int, completion_tokens: int):
        self.choices = [SimpleNamespace(message=message)]
        self.usage = SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            prompt_cache_hit_tokens=max(prompt_tokens - 1, 0),
            prompt_cache_miss_tokens=1,
        )


class AgentToolLoopTests(unittest.TestCase):
    def test_send_message_without_tools_keeps_single_completion_flow(self):
        agent = CacheAwareAgent(api_key="test", enable_tools=False)
        response = FakeResponse(
            SimpleNamespace(content="hello", tool_calls=None),
            prompt_tokens=8,
            completion_tokens=2,
        )
        agent._create_completion = lambda messages: response

        result = agent.send_message("hi")

        self.assertEqual(result["content"], "hello")
        self.assertEqual(result["metrics"].prompt_tokens, 8)
        self.assertIn("trace", result)
        self.assertIn("request_fingerprint", result["trace"])
        self.assertIn("history_role_counts_after", result["trace"])
        self.assertEqual(result["trace"]["request_message_count"], 2)
        self.assertEqual(result["trace"]["tool_rounds_executed"], 0)
        self.assertEqual(result["trace"]["tool_call_count"], 0)
        self.assertEqual(result["trace"]["tool_names_called"], [])
        self.assertEqual(result["trace"]["tool_execution_count"], 0)
        self.assertEqual(result["trace"]["tool_execution_results"], [])
        self.assertFalse(result["trace"]["tool_loop_terminated_by_max_rounds"])
        self.assertEqual(result["trace"]["pending_tool_calls_after_loop"], 0)
        self.assertEqual(len(agent.message_manager.get_api_messages()), 2)
        self.assertEqual(
            [message["role"] for message in agent.message_manager.get_api_messages()],
            ["user", "assistant"],
        )

    def test_send_message_with_tool_call_executes_read_file_loop(self):
        agent = CacheAwareAgent(api_key="test", enable_tools=True, max_tool_rounds=1)
        responses = [
            FakeResponse(
                SimpleNamespace(
                    content=None,
                    tool_calls=[FakeToolCall("call_1", "read_file", '{"file_path": "README.md"}')],
                ),
                prompt_tokens=10,
                completion_tokens=2,
            ),
            FakeResponse(
                SimpleNamespace(content="final answer", tool_calls=None),
                prompt_tokens=12,
                completion_tokens=3,
            ),
        ]
        agent._create_completion = lambda messages: responses.pop(0)

        result = agent.send_message("read the readme")
        messages = agent.message_manager.get_api_messages()

        self.assertEqual(result["content"], "final answer")
        self.assertEqual(result["metrics"].prompt_tokens, 22)
        self.assertEqual(result["metrics"].completion_tokens, 5)
        self.assertEqual(result["trace"]["tool_rounds_executed"], 1)
        self.assertEqual(result["trace"]["tool_call_count"], 1)
        self.assertEqual(result["trace"]["tool_names_called"], ["read_file"])
        self.assertEqual(result["trace"]["tool_message_count"], 1)
        self.assertEqual(result["trace"]["tool_execution_count"], 1)
        self.assertFalse(result["trace"]["tool_loop_terminated_by_max_rounds"])
        self.assertEqual(result["trace"]["pending_tool_calls_after_loop"], 0)
        self.assertEqual(result["trace"]["completion_round_count"], 2)
        self.assertEqual(result["trace"]["history_role_counts_after"]["tool"], 1)
        self.assertEqual(result["trace"]["tool_execution_results"][0]["tool_name"], "read_file")
        self.assertTrue(result["trace"]["tool_execution_results"][0]["success"])
        self.assertEqual(result["trace"]["tool_execution_results"][0]["status"], "ok")
        self.assertEqual(
            [message["role"] for message in messages],
            ["user", "assistant", "tool", "assistant"],
        )
        self.assertEqual(messages[2]["name"], "read_file")
        self.assertIn("README.md", messages[2]["content"])

    def test_send_message_marks_when_max_tool_rounds_stops_loop(self):
        agent = CacheAwareAgent(api_key="test", enable_tools=True, max_tool_rounds=0)
        response = FakeResponse(
            SimpleNamespace(
                content=None,
                tool_calls=[FakeToolCall("call_1", "read_file", '{"file_path": "README.md"}')],
            ),
            prompt_tokens=10,
            completion_tokens=2,
        )
        agent._create_completion = lambda messages: response

        result = agent.send_message("read the readme")

        self.assertTrue(result["trace"]["assistant_has_tool_calls"])
        self.assertTrue(result["trace"]["tool_loop_terminated_by_max_rounds"])
        self.assertEqual(result["trace"]["pending_tool_calls_after_loop"], 1)
        self.assertEqual(result["trace"]["pending_tool_names_after_loop"], ["read_file"])
        self.assertEqual(result["trace"]["tool_execution_count"], 0)
        self.assertEqual(result["trace"]["tool_execution_results"], [])
        self.assertEqual(result["trace"]["completion_round_count"], 1)

    def test_enabled_tool_schemas_only_include_supported_tools(self):
        agent = CacheAwareAgent(api_key="test", enable_tools=True)

        enabled_names = [schema["function"]["name"] for schema in agent._get_enabled_tool_schemas()]

        self.assertEqual(enabled_names, ["echo_json", "read_file"])


if __name__ == "__main__":
    unittest.main()
