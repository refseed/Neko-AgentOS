# Agent 系统架构设计报告（V2）

> 版本：`v2.0`  
> 更新日期：`2026-03-28`  
> 适用代码基线：当前 `main` 分支（含 `node-io/v1` 协议节点、共享 GraphEngine、交互式 CLI 调试链路）

## 0. 文档目的

本报告用于替代旧版架构说明中与当前代码不一致的部分，明确以下内容：

- 当前系统“已经落地”的架构形态（As-Is）。
- 当前实现中保留的设计原则与合理演进。
- 当前版本明确的边界、约束与后续演进方向。

本报告不追求“理想态描述”，优先保证与仓库代码一致。

## 1. 系统定位（当前版本）

NekoAgentCore 当前定位为：

- 一个面向复杂任务的 **状态驱动 Agent Runtime**；
- 主执行方式为 **Main Graph + 节点协议化输出 + 可暂停恢复**；
- 重点能力为：
  - 结构化路由（Meta/Strategist）；
  - 证据驱动调查（Investigation Subgraph）；
  - 审查与不确定性升级（Reflection + Break）；
  - 分层记忆（RAM/Cache/Disk/Blackboard）；
  - 配置文件驱动（`config/agent_os.toml`）。

## 2. 总体架构分层（As-Is）

当前代码按以下层次组织：

1. Interaction Layer  
`agent_os/app/cli.py` + `agent_os/app/services/orchestrator.py`  
负责交互菜单、`start-run/resume-run/run-regression`、暂停后继续输入。

2. Specification Layer  
`agent_os/runtime/state/blueprint_models.py` + `agent_os/runtime/graph/blueprint_loader.py`  
负责静态 Blueprint 图定义、阶段合法迁移、模板约束元数据。

3. Control Layer  
`agent_os/cognition/strategist/strategist.py`  
`agent_os/cognition/resource_manager/resource_manager.py`  
`agent_os/cognition/memory_router/memory_router.py`  
`agent_os/runtime/routing/capability_router.py`  
`agent_os/runtime/routing/meta_router.py`  
负责路由、模型挡位估计、记忆挂载计划、能力裁剪。

4. Cognition Layer  
`agent_os/cognition/prompt_builder/builder.py`  
`agent_os/cognition/reasoning/reasoning_node.py`  
`agent_os/cognition/reflection/reflection_node.py`  
`agent_os/cognition/clarification/question_node.py`  
负责 prompt 构造、推理、反思审查、用户交互文案构造。

5. Investigation Layer  
`agent_os/investigation/subgraph/runner.py` 及其子模块  
负责子图式检索、重排、抽取、证据审查与返回。

6. Memory Layer  
`agent_os/memory/ram/working_ram.py`  
`agent_os/memory/cache/episodic_cache.py`  
`agent_os/memory/disk/semantic_disk.py`  
`agent_os/memory/blackboard/global_blackboard.py`  
`agent_os/memory/compression/compressor.py`

7. Capability + Tool Layer  
`agent_os/tools/capability_loader/loader.py`  
`agent_os/tools/runtime/tool_runtime.py`  
`agent_os/tools/sandbox/sandbox.py`  
`agent_os/tools/registry/registry.py`

8. Execution Layer  
`agent_os/runtime/graph/engine.py`  
`agent_os/models/gateway/client.py`  
`agent_os/models/providers/*`

9. Governance / Observability Layer  
`agent_os/runtime/checkpoint/repository.py`  
`agent_os/runtime/epistemic_guard/guard.py`  
`agent_os/observability/tracing/trace_logger.py`  
`agent_os/observability/metrics/metrics.py`  
`agent_os/evaluation/*`

## 3. 主图与子图架构

### 3.1 Main Graph（当前主流程）

当前主图合法边：

- `interaction -> strategist`
- `strategist -> blueprint | reasoning | investigation | reflection | break | finish`
- `blueprint -> strategist | finish | break`
- `reasoning -> strategist | break`
- `investigation -> strategist | break`
- `reflection -> strategist | break`
- `break -> finish`
- `finish -> finish`

对应实现：`agent_os/runtime/graph/edges.py` + `agent_os/runtime/graph/engine.py`

### 3.2 Blueprint 在当前版本中的角色

Blueprint 当前为主图中的一个可路由节点，职责为：

- 激活当前 stage；
- 按 `transition_on_result` 决定下一 stage；
- 同步 `allowed_exits/subgraph_template/stage_status/stage_attempts`。

`subgraph_template` 在当前版本定位为“**执行约束元数据**”：

- 通过 `constrain_runtime_targets()` 限制 Strategist 可路由节点；
- 暂未实现为“不同模板实例化不同可执行子图代码”。

### 3.3 Investigation Subgraph（共享引擎）

Investigation 采用与主图同一套 `GraphEngine` 运行机制，区别是：

- 子图节点：`inv_query -> inv_recall -> inv_extract -> inv_review -> inv_return`
- `increment_budget=False`（不额外叠加主图步数）
- 使用独立 `InvestigationRuntimeContext` 承载回合内状态

这使主图/子图在“引擎能力”上统一，在“节点集合与边约束”上解耦。

## 4. 节点协议（node-io/v1）

### 4.1 协议目标

当前版本将模型驱动节点统一到协议化输出：

- `protocol_version = node-io/v1`
- `node_name`
- `confidence`
- `notes`
- 节点特定字段

基类：`agent_os/runtime/nodes/base.py` 中 `BaseLLMNode` + `NodeEnvelopeMixin`

### 4.2 协议化节点范围

当前已协议化或半协议化节点：

- `Strategist`（meta 路由输出）
- `PromptBuilderNode`
- `ReflectionNode`
- `SearchIntentNode`
- `ResultDistillNode`
- `InvestigationReviewNode`
- `MemoryCompressionNode`
- `MemoryForgettingNode`
- `ClarificationQuestionNode`（严格校验、可重试）

### 4.3 JSON 解析策略

`agent_os/models/json_parser.py` 采用：

- fenced JSON 提取；
- 首尾 `{...}` 候选提取；
- `json_repair` 修复回退。

Clarification 节点在此基础上增加：

- schema 校验；
- 语义校验（编号、可执行性、语言一致性）；
- 重试后失败即抛错（不 silent fallback）。

## 5. Control Plane 设计（当前实现）

### 5.1 Strategist

核心行为：

- 先做启发式路由（保证系统可运行）；
- 再调用模型路由；
- 低置信度触发更高挡位复核；
- 复核仍低置信度则进入 `break`。

模型挡位选择不再是静态表，而是基于：

- `context_chars`
- `task_complexity`
- `expected_output_tokens`
- `investigation_active`
- `accepted_fact_count`

### 5.2 ResourceManager

当前职责聚焦于：

- budget 允许性判定；
- 控制面调用挡位（`meta.control_model_tier`）。

### 5.3 MemoryRouter

当前输出“挂载计划”：

- strategist/reasoning/reflection 会挂载 blackboard；
- 按节点选择不同 detail level（L1/L2/L3）；
- 限定 RAM/Cache/Disk 挂载条目数。

### 5.4 CapabilityRouter + CapabilityLoader

流程为：

- `CapabilityRouter` 决定权限级别（`none/readonly/write`）；
- `CapabilityLoader` 按节点与权限暴露工具集合；
- `ToolRuntime` 执行时可再用 `allowed_tools` 二次约束。

## 6. Cognition 层职责边界（当前约定）

### 6.1 PromptBuilder

职责：把结构化状态转换为节点 prompt，不直接控制路由。

### 6.2 ReasoningNode

职责：

- 消费当前状态 prompt；
- 产出阶段草稿；
- 用结构化信号标记 `needs_investigation`。

当前默认策略：`accepted_facts` 为空时会触发调查需求。

### 6.3 ReflectionNode

职责：

- 通用审查上游节点输出；
- 输出 `approved/retry/need_more_evidence`；
- 给出 `interaction_requirements`（供后续用户交互节点使用）。

### 6.4 ClarificationQuestionNode

定位调整为：**用户交互表达节点**，而非“自己决定业务策略的节点”。

它接收上游形成的交互意图（pending items/uncertainty），再用模型生成面向用户的可执行交互文本。

## 7. 记忆体系（当前实现）

1. RAM：当前运行期高频短记忆（如最新草稿）。  
2. Cache：事件级轨迹缓存（append-only）。  
3. Disk：语义压缩后的持久记忆（L1/L2/L3）。  
4. Blackboard：稳定常量与全局约束（由配置注入）。

扩展能力：

- `memory_compression` 节点负责多粒度压缩；
- `memory_forgetting` 节点负责 cache 裁剪（带 LLM 策略）。

## 8. 执行、模型与流式输出

### 8.1 Model Gateway

`ModelGatewayClient` 统一对外响应：

- `text`
- `input_tokens/output_tokens`
- `estimated_cost_usd`
- `raw`

### 8.2 LiteLLM Provider

当前能力：

- 按 `small/medium/large` 映射模型；
- 可开启流式输出到控制台；
- 流式返回空文本时自动降级为非流式并熔断该模型流式；
- provider 异常时回退 EchoProvider 保障本地可运行。

## 9. Break / Checkpoint / Human-in-the-loop

1. 进入 `break` 节点时：

- 生成 checkpoint（SQLite + JSON snapshot）；
- 通过 EpistemicGuard 生成 `break_report`；
- 设置运行状态为 `paused`。

2. CLI 层在 paused 时：

- 展示 `question_for_user`；
- 支持直接输入补充信息并调用 `resume_run`。

3. `resume_run` 会：

- 将用户输入结构化追加为 `accepted_facts`；
- 必要时将 stage 状态回置为 `retry`；
- 从 `interaction` 节点重新进入主图。

## 10. 配置体系

当前策略：**运行参数由 TOML 配置驱动**（`config/agent_os.toml`）。

包含：

- runtime（步数、目录、快照）
- model（provider、模型映射、stream）
- investigation/blueprint/reflection/clarification
- capability/meta/blackboard

说明：

- 模型平台密钥依赖 provider 侧机制（例如 LiteLLM/SDK 读取环境变量）。
- 业务策略与行为阈值不应散落在环境变量中。

## 11. 当前版本的已知边界

为保证文档诚实性，当前仍有以下边界：

1. `subgraph_template` 当前主要用于“路由约束”，尚未完全做到“模板即执行实现”。  
2. `ReflectionNode` 仍保留启发式回退路径，用于协议输出异常时兜底。  
3. Clarification 严格协议下，若模型长期不遵守 JSON 契约会显式失败。  
4. 回归评估仍偏轻量，更多是运行正确性校验而非质量评分体系。  

## 12. V2 设计原则总结

当前版本坚持以下原则，并将作为后续迭代基线：

1. 主流程先“结构化状态正确”，再追求内容复杂度。  
2. 模型节点必须协议化，失败要可见、可诊断。  
3. 主图与子图共享引擎，减少执行语义分叉。  
4. 用户交互节点负责表达，不越权决定业务策略。  
5. 不确定性优先升级为显式交互，不静默猜测。  

