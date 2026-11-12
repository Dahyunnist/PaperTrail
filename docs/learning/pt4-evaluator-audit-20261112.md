# PT4 评测器偏差审计（2026-11-12）

## 审计范围

只跑 `tests/test_evaluate_qa.py`。其 PDF 由测试运行时合成，mock gold 与 mock QA 响应；未读私人 PDF、`.env` 或来源清单，未调用模型。

## 发现与修复

- 旧指标只核对 SHA 与页码。同一正确页上的错误短引文也会被算作目标页命中。
- 现分别输出目标页覆盖与精确 gold 引文覆盖。精确覆盖要求 SHA、页码一致，且引用文本包含 gold 最小 span。
- 增加空检索拒答、预算阻断不算正确拒答、部分回答不计为完整回答，以及评测调用不把 expected answer/evidence/abstain 传入 QA 的回归。

## 结果

定向测试 **7 passed**。关键负例中，错误短引文页级命中仍为 true，但精确引文命中为 0；这让旧页指标偏差可见，不再误报成完整引文证据。

复现：

```powershell
$env:PAPERTRAIL_LLM_MODEL = ''
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .tmp/pytest-pt4 tests/test_evaluate_qa.py
```

## 边界

评测器不把 gold 答案输入 QA；gold 内容仍会写入评测结果用于人工审计。精确 span 指标只对含 quote 字段的 gold evidence 计分；缺少 gold quote 时返回 null，不推断为零覆盖。mock 测试不证明真实问答质量或真实 PDF 引文质量。页码覆盖仍保留为独立检索指标，不代表引用正确。
