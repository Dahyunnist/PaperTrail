# PT-2：跨论文检索缺槽回归

日期：2026-11-13

## 行为

复杂比较问题拆成子问题后，每个检索结果保留其 `subquestion_ids`。回答只覆盖有证据的子问题；任一来源缺失时标记 `generated_partial`，列出缺失项，不为缺失来源生成引文。

## 验证

新增 `test_cross_paper_missing_retrieval_slot_stays_partial_without_fabricated_citation`。测试建立两份合成 PDF，模拟 Alpha 子问题命中、Beta 子问题无结果，并替身化规划与回答生成函数，不请求外部模型。断言缺槽状态、缺失子问题及引文哈希只对应 Alpha。

命令：`python -m pytest tests/test_s3.py::test_cross_paper_missing_retrieval_slot_stays_partial_without_fabricated_citation -q`

结果：`1 passed`。这验证代码契约，不代表真实论文 gold、真实模型质量或 PT-1 验收。

## 离线证据完整性回归补充

开发测试还覆盖最小完整证据集合、双来源 evidence slots、缺槽 partial，以及可答题被错误空拒答时状态为 refused 且不伪造 claim。新增 	est_answerable_question_with_wrong_empty_refusal_is_rejected 使用 fake generator；不会调用模型。相关测试文件：	ests/test_s3.py、	ests/test_evaluate_qa.py、	ests/test_p13_regressions.py、	ests/test_pt2_synthetic_retrieval.py。本轮相关测试 53 passed。它们使用合成 fixture，不替代真实论文盲测；PT-1 gold 仍为 0/40，禁止据此声称真实检索提升。

