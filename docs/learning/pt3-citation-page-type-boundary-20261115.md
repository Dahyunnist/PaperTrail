# PT-3 引文页码类型边界（2026-11-15）

## 发现与修复

`load_gold` 原用 `pdf_page < 1` 校验页码。Python 中 `bool` 是 `int` 子类，因此合成指针 `pdf_page: true` 会被当作第 1 页接受；后续 `verify_quotes` 也会用它索引第一页。来源 SHA、物理页和引文内容即使之后逐项检查，也无法修复输入类型已被错误接受的问题。

新增临时合成 JSONL 回归，先确认旧实现失败：`pytest.raises(ValueError)` 未触发。现校验页码必须是正整数且不能是布尔值；正常整数页码规则不变。

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q tests/test_gold.py::test_gold_rejects_boolean_pdf_page_in_synthetic_fixture tests/test_pt3_citation_failure_paths.py tests/test_pt3_adversarial_synthetic.py tests/test_s3.py::test_no_model_qa_abstains_when_retrieval_has_no_evidence tests/test_s3.py::test_cross_paper_claim_maps_each_citation_to_its_exact_source_span tests/test_s3.py::test_unanswerable_no_evidence_is_a_refusal_not_budget_block
```

结果：**8 passed**。合成测试覆盖错误来源 SHA、页码、quote、chunk/span 与 OCR 引文拒绝；无证据时空 claims 拒答；跨文献引文各自绑定原文来源。未运行模型。

## 冲突语义边界

现有跨文献回归证明多来源证据映射和逐段引用绑定，不证明系统能正确判断真实研究结果是否矛盾。冲突题的语义仲裁仍需人工核查和 PT-1 双人标注；本轮不增加自动冲突结论，也不据此报告 PT-3 质量指标。

本轮只读代码与合成测试，未读取私人 PDF、仓库 gold 或历史回答；未创建或修改 gold，未调用模型。PT-1 继续暂停。
