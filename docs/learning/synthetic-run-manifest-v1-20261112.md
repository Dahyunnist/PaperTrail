# PT2/PT4 合成运行 Manifest v1（2026-11-12）

PT2 与 PT4 合成评测采用共享 [run manifest v1 schema](../../evals/run-manifest-v1.schema.json) 和事件 trace。记录分别见 `evals/synthetic-run-manifests-v1.jsonl`、`evals/synthetic-run-traces-v1.jsonl`。

Manifest 固定代码提交 SHA、冻结数据/题集 SHA、prompt SHA、scorer SHA、split、Python/平台/依赖锁哈希、预算、状态及真实记录的开始/结束时间。纯离线 mock 运行用 `model_id: null`、`gold_source: synthetic_fixture`、`cost_usd: null`、prompt SHA 为 null，预算标为 `not_applicable`。这只代表 synthetic fixture 的离线测试，不代表真实 PDF 评测或 LLM 运行。

Trace 统一使用 `run_id`、`trace_id`、`span_id`、`event_name`、`timestamp`。当前标准事件为 `run.started`、`dataset.loaded`、`eval.case_completed`、`run.completed`、`run.failed`。Trace 不存全文、原始 prompt、私密路径或密钥；只存安全的状态与计数属性。`papertrail.run_manifest` 对必需 provenance、离线标记、事件名及隐私字段提供标准库校验。

回归覆盖合法 PT2/PT4 manifest 与 trace、缺少 scorer SHA、错误 offline 标记、全文/prompt/密钥/绝对路径泄漏、缺少 span ID 和非标准事件名。复现命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .tmp/pytest-manifest tests/test_run_manifest.py
```

当前 PT2 冻结小集 SHA 为 `003e7b11fc8ce3309cc12df140ce408b8f3f42ba58d52a4e093d0832c70a6269`；PT4 合成 scorer/test 输入 SHA 与运行信息在 manifest 中。SHA 指向已提交的代码版本。没有重跑真实论文或调用模型。
