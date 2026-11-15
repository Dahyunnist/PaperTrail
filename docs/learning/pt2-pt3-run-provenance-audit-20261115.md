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

## 确定性零调用记录补充（2026-11-15）

新增共享 manifest v2 schema。确定性 runner 的投影在 `shared_manifest_v2.usage` 记录 `request_count=0`、`response_count=0`、`cost_usd_estimate=0`、`status=observed_zero_requests`；原 `shared_manifest` v1 仍保留。`evaluation.usage` trace 同样逐事件记录这四项，并绑定本次 `run_id`、`trace_id`、独立 `span_id`。成功和失败运行均写入 usage 证据；只在设置 `PAPERTRAIL_TRACE_JSONL` 时落盘。无模型的 prompt、tool schema、runtime digest 与 token/step 限额继续按原规则标记不适用。

v2 投影没有显式 usage 依据时保留 `usage=null`；若费用也未记录，`cost_usd_estimate=null`。历史模型报告不迁移、不回填。新增定向验证：

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .codex-test-tmp tests/test_shared_manifest.py tests/test_evaluate_run.py tests/test_run_manifest.py tests/test_pt1_human_csv_import.py
```

结果：**47 passed**。覆盖 v2 schema/投影、未知费用保持 null、trace 零调用字段及合成 CSV→确定性报告链路。

用户提供的历史账单汇总仅作人民币历史用量旁证：PaperTrail 别名 245 次、¥0.30348732；全量导出 4,402 次、¥10.91277486，导出成本合计一致。它与美元评测预算分开，不代表当前余额。别名 0815 的 1,471 次不可分配；未将其归入 PaperTrail，也未复制原始账单、用户标识或密钥字段。

## Trace 白名单稳健性补充（2026-11-15）

Trace emitter 现只投影事件白名单内的标量字段；未知字段和非标量值静默丢弃。`query`、`path` 不写入 trace，也不会因遥测参数导致业务调用抛错。`evaluation.usage` 零调用字段仍在显式白名单内。

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_runtime_trace.py tests/test_shared_manifest.py tests/test_evaluate_run.py tests/test_run_manifest.py tests/test_pt1_human_csv_import.py tests/test_pt2_synthetic_retrieval.py tests/test_pt3_citation_failure_paths.py tests/test_pt3_adversarial_synthetic.py
```

结果：**57 passed**。新回归验证白名单外的 `query`/`path` 与非标量 `mode` 不落盘，trace 调用正常返回。
