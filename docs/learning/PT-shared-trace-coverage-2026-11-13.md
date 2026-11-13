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
