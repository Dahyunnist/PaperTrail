# PT3 离线安全闭环（2026-11-12）

## 范围

仅使用测试运行时生成的合成 PDF 和 mock 模型响应。测试进程显式清空 `PAPERTRAIL_LLM_MODEL`，所有生成路径均由 monkeypatch 替代；无外部模型请求。未读取 `.env`、私人 PDF 或来源 manifest。

## 结果

`tests/test_s3.py` 与 `tests/test_p13_regressions.py` 定向运行：**41 passed**。

- 部分证据时保留已支持 claim，并标出未覆盖要点。
- 每条 claim 绑定检索证据的版本 SHA、页码、精确原文 span。
- unsupported claim、错误 SHA、越界页码和 OCR 派生引用均拒绝。
- 错误的子问题/证据槽映射不计入完整覆盖。

机器可读结果见 `evals/pt3-offline-safety-report-20261112.json`。复现命令：

```powershell
$env:PAPERTRAIL_LLM_MODEL = ''
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .tmp/pytest-pt3 tests/test_s3.py tests/test_p13_regressions.py
```

## 结论与限制

现有代码已具备上述拒绝与部分回答行为，本阶段补充可复现报告，没有重复实现功能。结果只证明合成 fixture 上的离线控制流和 mock 审查路径；不证明真实问答质量提升、真实来源引用正确率或跨文献泛化。
