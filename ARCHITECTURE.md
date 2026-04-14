# Architecture Design

## 概述

本项目实现了一个缓存友好的 Agent 架构，核心目标是最大化 prompt caching 命中率，降低 API 成本。设计灵感来自 Claude Code 的分层 prompt 架构。

## 四层架构设计

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Static System Prompt                              │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ - Agent 角色定义                                         │ │
│ │ - 工具使用指南                                           │ │
│ │ - 行为规范                                               │ │
│ │ 特点: 会话内完全不变，100% 可缓存                        │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Session Configuration (Latched)                   │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ - model: "deepseek-chat"                                │ │
│ │ - temperature: 0.7                                      │ │
│ │ - max_tokens: 1024                                      │ │
│ │ - timestamp: "2026-04-14T..."                           │ │
│ │ 特点: 会话开始时锁定，之后不可修改                       │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Tool Schema Cache                                 │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ - 确定性序列化 (sort_keys=True)                         │ │
│ │ - 按名称排序返回                                         │ │
│ │ - 会话内保持稳定                                         │ │
│ │ 特点: 注册后不变，schema 顺序确定                        │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Layer 4: Append-Only Message History                       │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ [user] "What is prompt caching?"                        │ │
│ │ [assistant] "Prompt caching is..."                      │ │
│ │ [user] "How does it work?"                              │ │
│ │ [assistant] "It works by..."                            │ │
│ │ 特点: 只能追加，禁止修改/删除，保护缓存前缀              │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 核心设计原则

### 1. 前缀稳定性 (Prefix Stability)

**问题**：Prompt caching 基于前缀匹配。如果请求的前缀部分发生变化，缓存失效。

**解决方案**：
- Layer 1-3 在会话内保持完全稳定
- Layer 4 只能追加，不能修改历史
- 每次请求的前缀都是上一次请求的超集

**效果**：
```
Turn 1: [system] + [session] + [tools] + [msg1]
Turn 2: [system] + [session] + [tools] + [msg1] + [msg2]  ← 前缀完全匹配
Turn 3: [system] + [session] + [tools] + [msg1] + [msg2] + [msg3]  ← 前缀完全匹配
```

### 2. 确定性序列化 (Deterministic Serialization)

**问题**：Python dict 默认无序，JSON 序列化结果不稳定，导致相同内容产生不同字符串。

**解决方案**：
```python
# 所有 JSON 序列化都使用
json.dumps(data, sort_keys=True, ensure_ascii=False)

# Tool schema 按名称排序
sorted_names = sorted(self._cache.keys())
return [json.loads(self._cache[name]) for name in sorted_names]
```

**效果**：相同的数据结构总是产生相同的字符串，保证缓存命中。

### 3. Append-Only 消息历史

**问题**：修改或删除历史消息会破坏缓存前缀。

**解决方案**：
```python
class AppendOnlyMessageManager:
    def append(self, message: Message) -> None:
        """唯一允许的修改操作"""
        self._messages.append(message)
    
    def pop(self, *args, **kwargs) -> None:
        """禁止 pop 操作"""
        raise RuntimeError("Cannot pop messages! Message history must be append-only.")
```

**效果**：
- 消息历史只增不减
- 缓存前缀永远有效
- 即使在边界情况（如 max_tool_rounds 限制）也通过追加 dummy responses 保持不变性

### 4. Session 配置锁存 (Configuration Latching)

**问题**：会话中途修改 model/temperature 会导致请求格式变化，破坏缓存。

**解决方案**：
```python
@dataclass(frozen=True)
class SessionConfig:
    """Immutable session configuration"""
    model: str
    temperature: float
    max_tokens: int
    timestamp: str
```

**效果**：配置在会话开始时确定，之后无法修改。

## 工具执行层设计

### 路径安全

所有文件操作工具都限制在 workspace 内：

```python
def ensure_within_workspace(self, path: Path) -> None:
    if not path.is_relative_to(self.workspace_root):
        raise ToolExecutionError(
            code="path_not_allowed",
            message="Access denied outside workspace root.",
        )
```

### 确定性输出

工具返回结果保持确定性：
- `list_directory`: 按名称排序
- `search_content`: 按行号排序
- 所有 JSON 输出使用 `sort_keys=True`

### 结构化错误

统一的错误格式：
```json
{
  "code": "file_not_found",
  "message": "Requested file does not exist.",
  "details": {
    "requested_path": "/path/to/file"
  }
}
```

## 多轮工具编排

### 问题：max_tool_rounds 限制

当达到 `max_tool_rounds` 限制时，assistant 可能还有未执行的 tool calls，导致对话状态无效。

### 解决方案：Dummy Tool Responses

不删除消息（违反 append-only），而是追加 dummy responses：

```python
if tool_loop_terminated_by_max_rounds:
    # 为所有 pending tool calls 追加 dummy responses
    for tool_call in assistant_message.tool_calls:
        self._append_tool_message(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            content=json.dumps({
                "status": "skipped",
                "error": {
                    "code": "max_tool_rounds_exceeded",
                    "message": "Tool execution skipped: max_tool_rounds=1 reached"
                }
            })
        )
    
    # 强制最终 completion（不带 tools）
    final_response = self._create_completion(messages, tools=[])
```

### 效果

- 保持 append-only 不变性
- 完整的执行轨迹（包括被跳过的工具）
- 对话状态始终有效

## 实验框架设计

### 双轨实验

**schema-only 轨道**：
- 只注册 tool schemas，不执行
- 验证 schema 稳定性对缓存的影响

**execution-enabled 轨道**：
- 真实执行工具
- 验证工具调用序列的确定性

### Cache Breakers

测试不同破坏缓存的因素：
1. **Modify Message History**: 修改历史消息
2. **Modify Session Config**: 修改会话配置
3. **Modify Tool Schema**: 修改工具定义
4. **Non-Deterministic Serialization**: 非确定性序列化

### 可重复性

- 固定 seed
- 多次重复实验
- 聚合统计（mean ± std）

## 性能指标

### 缓存命中率

```
cache_hit_rate = cache_hit_tokens / (cache_hit_tokens + cache_miss_tokens)
```

### 成本估算

基于 DeepSeek API 定价：
- Cache write: $0.14 / 1M tokens
- Cache read: $0.014 / 1M tokens (10x cheaper)
- Regular: $0.14 / 1M tokens

### 实验结果

**Baseline (稳定架构)**:
- Cache Hit Rate: 97.98%
- Total Cost: $0.0024

**Modify Message History**:
- Cache Hit Rate: 19.21% (↓ 78.77%)
- Total Cost: $0.0098 (↑ 4.1x)

**Multi-Turn Tools (max_rounds=1 vs 2)**:
- max_rounds=1: 96.47% hit rate, $0.0017
- max_rounds=2: 80.60% hit rate, $0.0093 (5.5x more expensive)

## 技术栈

- **语言**: Python 3.11+
- **API**: OpenAI-compatible (DeepSeek)
- **测试**: unittest
- **可视化**: matplotlib

## 设计权衡

### 优势
- 极高的缓存命中率（>95%）
- 显著降低 API 成本（70%+）
- 完整的可观测性
- 严格的类型安全

### 限制
- Append-only 限制了某些高级功能（如消息编辑）
- 工具集较小（为了保持确定性）
- 不支持 streaming（会破坏缓存前缀）

### 适用场景
- 多轮对话 Agent
- 工具调用密集型任务
- 成本敏感的应用
- 需要高可重复性的场景

## 未来改进方向

1. **更多工具**: 在保持确定性的前提下扩展工具集
2. **并行工具调用**: 支持同时执行多个独立工具
3. **流式输出**: 探索与缓存兼容的 streaming 方案
4. **分布式缓存**: 跨会话共享缓存前缀
