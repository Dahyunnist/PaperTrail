# PT-2/PT-3 离线 CSV 与评测来源审计（2026-11-15）

## 本轮改动

确定性 runner 原先将 `evaluate_run.py` 自身摘要当作 `scorer_sha`。现改为对实际指标实现 `papertrail/evaluate.py` 求 SHA-256；合成端到端测试逐字节核对该来源。无模型检索没有 agent 步数，manifest 现在将 `max_steps` 留为 `null`，共享投影标为 `not_applicable`。

CSV 导入和确定性评测的离线回归继续只用测试生成的临时 CSV、PDF 与 gold fixture。PT-2 合成检索和 PT-3 引用测试覆盖报告生成、来源绑定及失败路径。定向命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .codex-test-tmp tests/test_pt1_human_csv_import.py tests/test_evaluate_run.py tests/test_shared_manifest.py tests/test_pt2_synthetic_retrieval.py tests/test_pt3_citation_failure_paths.py tests/test_pt3_adversarial_synthetic.py
```

结果：**44 passed**。没有运行真实 PT-2 gold、PT-1 pending CSV、私人 PDF 或模型。没有创建或更改 gold，也没有重写历史报告。

## 来源边界

- 当前确定性 runner 的 `run_id`、`trace_id` 来自本次运行时间、HEAD SHA 与冻结 gold SHA；trace 事件在绑定上下文内继承两者，并为每个事件生成独立 `span_id`。失败事件由 runner 显式记录。是否落盘仍取决于 `PAPERTRAIL_TRACE_JSONL`。
- 当前 runner 明确 `model_id=none`，因此 `cost_usd_estimate=0` 表示本运行无模型调用；它不代表未知模型成本为零。报告没有请求计数指标，trace schema 也没有请求计数/费用字段，不从缺失 trace 推导请求数或成本。
- prompt、tool schema、runtime digest、max tokens 对无模型检索不适用；span 不在 run manifest 中记录。各字段由共享 manifest 标为 `not_applicable` 或 `not_recorded`，不会填造摘要。runtime digest 仍为空，因为本 runner 未绑定 lock 描述符。
- 既有自定义 runner 与历史模型报告没有统一 manifest/trace 关联。其历史模型调用数仅能引用原报告的 usage 字段，不能与 trace 关联或补写费用、run ID。历史证据保持原样；本审计不推断所有 runner 已接入。

测试仅证明合成 fixture 下的导入拒绝、确定性报告和 manifest 来源契约。它不证明 gold 内容正确，也不是 PT-2/PT-3 真实语料质量结果。PT-1 真实双人 gold 仍待标注和独立复核。
