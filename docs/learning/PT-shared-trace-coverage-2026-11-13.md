# PT 共享 Trace 覆盖（2026-11-13）

核对 `papertrail/trace.py` allowlist、事件发射点、对应回归和本阶段运行记录。`not_covered` 表示无统一事件或无对应测试；`not_observed` 表示本阶段没有真实触发记录。代码/测试存在不等于运行时发生。

| 事件 | 实现 | 回归覆盖 | 本阶段实跑 |
|---|---|---|---|
| timeout | not_covered；HTTP 客户端有 timeout 参数，无统一事件 | not_covered | not_observed |
| retry | QA 有重试逻辑，未发统一事件 | `tests/test_p13_regressions.py` 覆盖结构修复重试 | not_observed |
| budget_exceeded | 本地模型预算守卫有拒绝逻辑，未发统一事件 | `tests/test_local_llm.py` 覆盖预算拒绝 | not_observed |
| unsafe_action_blocked | not_covered | not_covered | not_observed |
| cancel | not_covered | not_covered | not_observed |
| checkpoint_resume | 个别脚本有恢复流程，无统一事件 | 局部恢复测试；统一事件 not_covered | not_observed |

现有 `trace.emit` 仅接受 retrieval、rerank、generation、citation、access 和 human review 事件。私有 query、路径、全文、prompt 不进入允许字段。此次不扩展事件协议；先将覆盖边界留档，避免把离线合成测试误报成实跑事件。

本次仅运行 `tests/test_runtime_trace.py`，结果见提交记录；没有模型请求、私人材料读取或运行时异常事件触发。

## 生命周期事件离线补充（2026-11-16）

Trace allowlist 与 manifest validator 新增 `timeout`、`retry`、`budget_exceeded`、`checkpoint_resume` 及标量字段校验。发射点只放在模型客户端捕获超时、QA 启动一次真实修复重试、预算守卫拒绝请求、索引任务从 running 恢复为 queued 的状态转移处。`recover_jobs` 仅在更新行数大于零时发出恢复事件。

合成回归使用 stub 生成器和临时 SQLite；22 项通过，1 项本机 loopback Ollama 测试按选择器排除。没有模型请求或服务端运行记录。`unsafe_action_blocked` 暂无对应危险动作执行/拦截业务路径；`cancel` 暂无任务取消状态转移；二者仍未覆盖，不伪造事件。

## MCP 工具事件离线补充（2026-11-16）

核查 `papertrail/mcp_server.py` 后，确认 `tools/call` 有真实工具选择、执行及拒绝分支。新增 `tool.selected`、`tool.executed` 事件，只记录 allowlist 工具名、完成/拒绝状态及异常类型，不记录参数、查询、SHA 或路径。stdio 合成回归覆盖两个只读工具、成功和拒绝结果，并检查 trace 不含查询词。

当前没有取消请求的状态转移，也没有危险动作工具或拦截业务路径。因此 `cancel` 与 `unsafe_action_blocked` 仍未覆盖。此为离线合成回归，不代表生产调用记录。
