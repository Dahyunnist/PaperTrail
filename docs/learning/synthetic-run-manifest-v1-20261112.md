# PT2/PT4 合成运行 Manifest v1（2026-11-12）

PT2 与 PT4 合成评测采用共享 [run manifest v1 schema](../../evals/run-manifest-v1.schema.json) 和事件 trace。记录分别见 `evals/synthetic-run-manifests-v1.jsonl`、`evals/synthetic-run-traces-v1.jsonl`。

Manifest 固定代码提交 SHA、冻结数据/题集 SHA、prompt SHA、scorer SHA、split、Python/平台/依赖锁哈希、预算、状态及真实记录的开始/结束时间。纯离线 mock 运行用 `model_id: null`、`gold_source: synthetic_fixture`、`cost_usd: null`、prompt SHA 为 null，预算标为 `not_applicable`。这只代表 synthetic fixture 的离线测试，不代表真实 PDF 评测或 LLM 运行。

Trace 统一使用 `run_id`、`trace_id`、`span_id`、`event_name`、`timestamp`。当前代码允许的事件为 `retrieval.completed`、`rerank.completed`、`generation.completed`、`citation.validated`、`access.checked`、`human.reviewed`、`evaluation.failed`、`evaluation.usage`，以及 2026-11-16 增补的 `timeout`、`retry`、`budget_exceeded`、`checkpoint_resume`。此 JSONL 样本包含前六类事件；不代表其余事件在该运行中发生。Trace 不存全文、原始 prompt、私密路径或密钥；只存安全的状态与计数属性。`papertrail.run_manifest` 对必需 provenance、离线标记、事件名及隐私字段提供标准库校验。

回归覆盖合法 PT2/PT4 manifest 与 trace、缺少 scorer SHA、错误 offline 标记、全文/prompt/密钥/绝对路径泄漏、缺少 span ID 和非标准事件名。复现命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .tmp/pytest-manifest tests/test_run_manifest.py
```

当前 PT2 冻结小集 SHA 为 `003e7b11fc8ce3309cc12df140ce408b8f3f42ba58d52a4e093d0832c70a6269`；PT4 合成 scorer/test 输入 SHA 与运行信息在 manifest 中。SHA 指向已提交的代码版本。没有重跑真实论文或调用模型。

## 横向交付要求核对（2026-11-16）

- Manifest v1/v2 投影包含路线 8.1 所列代码、数据、split、模型、prompt/tool/runtime、预算、评分器、gold source、费用、run/trace/span ID、时间、状态与 `field_status`。无模型运行把 prompt/tool/runtime/token 限额标为 `not_applicable`；未观测费用保留 null。`tests/test_shared_manifest.py` 与 `tests/test_evaluate_run.py` 验证投影及失败报告，合计 **42 passed**。
- trace 事件共享 run/trace/span ID 并按白名单过滤敏感内容；当前事件并非完整 OTel 父子 span 图。`tool_selection`、`tool_execution`、`cancel`、`unsafe_action_blocked` 尚无统一事件/真实触发路径。`timeout`、`retry`、`budget_exceeded`、`checkpoint_resume` 已有代码发射和合成回归，但本文件中的静态 JSONL 没有这些真实触发记录。
- README 指向 PT-4 离线复现文档；五分钟演示列出复现步骤和质量边界，PT-3 阶段文档提供 Mermaid 架构图。它们不替代真实质量验收。PT-1 双人 gold 继续暂停；PT-2 检索质量、PT-3 语义支持/拒答质量和实际触发 trace 的运行证据仍待人工数据或受控运行。

本核对只查看代码、文档和已提交 synthetic manifest/trace；未读取真实 gold、私人 PDF、账单，未调用模型。
