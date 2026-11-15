# PT-3 评测结果分类回归（2026-11-15）

## 路线对照与证据

2026-10-23 的 [PT-3 阶段记录](stage-PT3.md)要求评估 claim 支持、正确拒答、错误作答和生成失败；当前 [PT-2/PT-3 收尾记录](pt2-pt3-offline-closeout-20261114.md)也明确预算阻断不能算正确拒答。

代码已让 `_correct_abstention` 排除 `budget_blocked`，但逐题 `_outcome_class` 没有单独处理它。对预期不可回答题，预算阻断被写为 `false_answer`；对预期可回答题，无 claim 的预算阻断会写为 `answered`。这把“没有执行回答”误报成答案质量结果。

先加回归，再运行时确认失败：

```text
assert _outcome_class({"answered": False, "completion_state": "budget_blocked"}, True) == "budget_blocked"
E AssertionError: assert 'false_answer' == 'budget_blocked'
```

## 修复与验证

`_outcome_class` 现在优先将 `budget_blocked` 和 `failed` 各自保留为独立类别。正确拒答、错误拒答及错误作答分类不变。历史评测报告未改写。

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_evaluate_qa.py tests/test_s3.py::test_qa_marks_budget_blocked_separately_from_model_refusal tests/test_s3.py::test_unanswerable_no_evidence_is_a_refusal_not_budget_block tests/test_s3.py::test_answerable_question_with_wrong_empty_refusal_is_rejected tests/test_pt3_citation_failure_paths.py tests/test_pt3_adversarial_synthetic.py
```

结果：**14 passed**。评测集加载由 fixture 替身提供；PDF 为临时合成文件；评测集成测试将证据筛选与合成替身都显式 stub，不调用模型。其他回归只测纯分类函数、临时合成 PDF 或 citation fixture。

本次未读取私人 PDF、仓库 gold 或历史回答内容；未创建或修改 gold，未调用模型。结果仅证明分类规则正确，不代表真实 PT-3 质量或盲测结果。PT-1 继续暂停。
