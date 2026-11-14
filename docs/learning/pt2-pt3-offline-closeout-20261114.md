# PT-2/PT-3 离线收尾核对（2026-11-14）

本轮只核对代码、学习记录和合成测试，不打开论文 PDF、读取/修改 gold 文件或调用模型。PT-1 仍为 0/40，等待两位标注者提交独立 A/B 文件并完成仲裁。

## PT-2 检索与完整证据集合

- 当前冻结合成集是 3 个 query，BM25、dense、RRF 共 9 个方法运行；现有报告均找到各自最小证据集合，重复运行 JSONL 与报告 SHA 一致。报告 SHA-256：`9602c21652c5413cea79c6e8d980b1692ecd669a652f6099e575f5d52ea09650`。
- 本项目报告中的 `dense` 是字符 TF-IDF + SVD；它不是神经 embedding，也不是 BGE。rerank 排序测试用 monkeypatch 验证输入/输出契约，不代表真实 reranker 质量。
- 旧 7/10 完整证据覆盖及两篇显式来源修复（Recall@20 4/4）仍是已见开发集事后诊断；不构成本轮实测、盲测或泛化提升。
- 完整证据评估对每条 expected evidence 单独核对命中 SHA/页和规范化 quote，再计算 `complete_evidence_at_k`、`evidence_item_recall_at_k` 与所有预期页覆盖。当前回归包含多来源页覆盖和错误 quote 不计精确引用。

## PT-3 回答、拒答与引用安全

现有 fake-generator/合成夹具回归覆盖：缺来源槽时保留部分回答并标出缺项、不生成缺失来源引用；可答题的错误空拒答会被拒绝；无证据的不可答题走拒答路径且不与预算阻断混淆；claim 必须映射到同一子问题槽并通过 SHA、页和原文 quote 检查。旧 PT17 模型结果仍只作为历史诊断，不是当前模型表现或 PT-1 质量验收。

## 本轮验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .codex-test-tmp tests/test_pt2_synthetic_retrieval.py tests/test_pt3_citation_failure_paths.py tests/test_semantic_rerank.py tests/test_evaluate_qa.py::test_expected_page_metrics_require_all_pages_for_multi_source_answers tests/test_evaluate_qa.py::test_same_page_with_wrong_quote_does_not_count_as_exact_evidence tests/test_evaluate_qa.py::test_partial_answer_does_not_count_as_complete_answer tests/test_s3.py::test_cross_paper_missing_retrieval_slot_stays_partial_without_fabricated_citation tests/test_s3.py::test_complex_ask_retrieves_each_subquestion_and_keeps_partial_answer tests/test_s3.py::test_qa_drops_claim_when_deterministic_evidence_mapping_fails tests/test_s3.py::test_unanswerable_no_evidence_is_a_refusal_not_budget_block tests/test_s3.py::test_answerable_question_with_wrong_empty_refusal_is_rejected tests/test_p13_regressions.py::test_decomposed_same_paper_evidence_keeps_each_required_slot tests/test_p13_regressions.py::test_claim_cannot_cover_subquestion_with_evidence_from_another_slot
```

结果：**19 passed**。本轮未发现可复现且应修改的 PT-2/PT-3 代码缺口，因此未改实现和任何 gold。PT-2/PT-3 的合成与 mock 证据只证明离线契约；真实检索/回答质量仍依赖人工完成的 PT-1 gold，并须另行预登记和验收。
