# 项目总结与面试要点

## 一句话总结

设计并实现了一个缓存友好的 LLM Agent 架构，通过四层分离和 append-only 约束，将缓存命中率从 11% 提升到 88%，并通过可重复实验量化了不同设计决策的影响。

## 核心成果

1. **架构设计**：四层缓存友好架构（静态 prompt、配置层、工具层、历史层）
2. **实验验证**：5 轮 × 5 次重复实验，量化了 cache breakers 的影响
3. **工程质量**：29 个单元测试，完整的可观测性，确定性输出
4. **成本优化**：正确实现可达 88% 命中率，错误实现仅 11%（差距 7 倍）

## 技术深度展示点

### 1. 系统设计能力

**问题识别**：
- Prompt caching 基于前缀匹配，任何前缀变化都会导致缓存失效
- Python dict 无序、消息历史可变、配置可修改都是潜在的 cache breaker

**架构方案**：
- 四层分离：静态层 100% 可缓存，配置层锁存，工具层确定性，历史层 append-only
- 通过类型系统和运行时检查保证约束（`@dataclass(frozen=True)`、魔术方法禁止修改）

**权衡取舍**：
- 牺牲灵活性（不能修改历史、不能动态改配置）换取缓存稳定性
- 边界情况处理（max_tool_rounds 限制时追加 dummy responses 而非破坏 append-only）

### 2. 实验方法论

**对比实验设计**：
- Baseline：正确实现
- Cache Breakers：每次只改变一个变量
- 双轨验证：schema-only（纯架构）+ execution-enabled（真实场景）

**可重复性**：
- 固定 seed、多次重复、聚合统计
- 结构化输出便于自动化分析
- 完整的 trace 记录支持事后分析

**数据驱动**：
- 非确定性序列化使命中率暴跌 77%（超出预期）
- max_tool_rounds=2 比 max_tool_rounds=1 贵 5.5 倍
- 用数据支撑设计决策

### 3. 工程实践

**测试覆盖**：
- 29 个单元测试覆盖核心逻辑
- 边界情况测试（空文件、路径安全、append-only 约束）
- 所有测试通过才能提交

**可观测性**：
- 每轮对话记录完整 trace（工具调用、缓存指标、执行结果）
- 结构化错误码（file_not_found、path_not_allowed、max_tool_rounds_exceeded）
- 支持追踪工具执行成功率、截断情况

**代码质量**：
- 类型注解、文档字符串
- 确定性输出（sort_keys、按名称排序）
- 清晰的抽象层次（PromptManager、MessageManager、ToolCache、ToolExecutor、Agent）

## 面试话题点

### 如果面试官问："你遇到的最大挑战是什么？"

**max_tool_rounds 边界情况处理**：

问题：当达到 max_tool_rounds 限制时，assistant 可能还有未执行的 tool calls，导致对话状态无效（API 会报错）。

初版方案：直接 pop 掉最后一条消息 → 违反 append-only 核心约束

最终方案：追加 dummy tool responses（status="skipped"）→ 保持 append-only 不变性，同时解决 API 状态问题

收获：不能为了方便破坏核心设计原则，要找到符合架构约束的解决方案。

### 如果面试官问："如果让你继续做，你会做什么？"

**短期（1-2 周）**：
1. 增加实验维度（temperature 影响、prompt 长度影响）
2. 对比不同 LLM 的缓存表现（Claude vs GPT vs DeepSeek）
3. 测试更复杂的工具编排场景

**中期（1-2 月）**：
1. 实现 streaming 支持（保持缓存友好）
2. 添加 retry 机制和 token 预算控制
3. 支持更多工具类型（HTTP、数据库）

**长期（生产化）**：
1. 分布式缓存共享（多 agent 共享 prompt cache）
2. 自适应 max_tool_rounds（根据任务复杂度动态调整）
3. 成本监控和告警

### 如果面试官问："你从这个项目学到了什么？"

1. **架构约束的价值**：通过编译期和运行时约束保证正确性，比依赖开发者自觉更可靠
2. **实验驱动设计**：数据比直觉更可靠，非确定性序列化的影响超出预期
3. **边界情况处理**：不能为了方便破坏核心原则，要找到符合架构的解决方案
4. **可观测性的重要性**：完整的 trace 让问题定位和性能分析变得简单

## 项目亮点（简历用）

- 设计并实现缓存友好的 LLM Agent 架构，通过四层分离和 append-only 约束将缓存命中率从 11% 提升到 88%
- 通过可重复实验（5 轮 × 5 次）量化了非确定性序列化、消息历史修改等 cache breakers 的影响
- 实现完整的工具编排系统，支持多轮工具调用，包含路径安全、结构化错误、确定性输出
- 29 个单元测试覆盖核心逻辑，完整的可观测性（trace、metrics、tool execution results）

## 技术栈

- Python 3.13
- DeepSeek API (prompt caching)
- 类型系统（dataclass、type hints）
- 单元测试（unittest）
- 数据分析（JSON、统计聚合）
