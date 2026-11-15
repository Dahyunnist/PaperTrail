# PT-2 确定性评测 k 参数校验（2026-11-15）

## 路线与现有覆盖

2026-10-23 的 [PT-2 阶段记录](stage-PT2.md)要求按 k 报告页面召回、MRR 和完整证据。复核现有合成回归后，确认多页 evidence slots 已区分页覆盖与完整引文；PT-3 citation 测试和过期版本测试也已覆盖 SHA/页码失效，拒答测试已区分 false refusal 与 budget block。这些路径本轮未改。

发现 PT-2 的 `evaluate()` 和 `compare_modes()` 未验证 k。k=0 时仍先读 gold；继续执行时，`_unique_pages(results, 0)` 可能返回一页，使“@0”产生非空结果。负数、布尔值和非整数也没有明确拒绝契约。

先加参数化回归，当前代码对四种非法 k 均在读取缺失 gold 时抛出 `FileNotFoundError`，未按接口契约拒绝：

```text
tests/test_evaluate.py::test_evaluation_rejects_nonpositive_k_before_reading_inputs
4 failed: expected ValueError("k must be >= 1"); got FileNotFoundError
```

## 修复与验证

`evaluate()` 与 `compare_modes()` 现在在读 gold 或数据库前验证 k 必须是正整数；明确拒绝布尔值和小数。

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_evaluate.py tests/test_evaluate_qa.py tests/test_pt2_synthetic_retrieval.py tests/test_pt2_hybrid_version_lifecycle.py tests/test_pt3_citation_failure_paths.py tests/test_pt3_adversarial_synthetic.py tests/test_s3.py::test_qa_marks_budget_blocked_separately_from_model_refusal tests/test_s3.py::test_unanswerable_no_evidence_is_a_refusal_not_budget_block tests/test_s3.py::test_answerable_question_with_wrong_empty_refusal_is_rejected tests/test_access_control.py::test_answer_eval_jsonl_rejects_expired_claim_source tests/test_pt4_acl_retrieval_regressions.py::test_replaced_and_deleted_citations_expire_and_incremental_rebuild_recovers
```

结果：**30 passed**。测试只使用临时合成 PDF/gold、合成数据库、stubbed QA 与纯分类用例；不调用模型。未读取或修改冻结 gold、历史报告或私人 PDF。PT-1 继续暂停。
