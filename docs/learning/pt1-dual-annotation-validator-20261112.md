# PT-1 双人独立标注校验器

可填写的 A/B 工作表、许可来源字段及分论文冻结清单见 [双人填写导出说明](pt1-dual-export-and-frozen-list-20261112.md)。

校验器读取现有空白任务 CSV、候选来源清单和一份离线 JSONL 标注副本。原始 CSV 继续保持空白；不要把标注写回模板。

每道题至少提交两条记录，`annotator_id` 不同，且每条显式声明 `independent: true`。这是标注者对独立作答的声明，工具不能验证现实身份或作答过程。记录格式见 `evals/pt1-dual-annotation-schema-v1.json`。

合成记录示例：

```json
{"task_id":"PT1-H001","annotator_id":"reviewer-a","independent":true,"doi":"10.0000/synthetic","pdf_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","question":"合成研究纳入多少人？","question_type":"fact_location","answerability":"answerable","expected_answer":"12人。","minimum_complete_evidence_set":true,"evidence":[{"doi":"10.0000/synthetic","pdf_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","pdf_page":1,"start_char":0,"end_char":10,"quote":"合成研究纳入12人。","relation":"supports"}]}
```

`answerability` 由人判断，可填 `answerable`、`unanswerable` 或 `ambiguous`。不可答题须在 `expected_answer` 写拒答理由，且 evidence 留空。可答题须列出完整最小证据集，并人工确认 `minimum_complete_evidence_set: true`。页码用 PDF 物理页码；span 是该页 PyMuPDF 文本的 Unicode 字符 `[start_char,end_char)`。

运行完整 40 题批次：

```powershell
.\.venv\Scripts\python.exe scripts/validate_pt1_dual_annotations.py <双人标注.jsonl> --tasks evals/pt1-human-annotation-task-40-20261111.csv --manifest evals/pt1-candidate-manifest-20261111.json --report .local/pt1-adjudication-status.jsonl
```

填写导出表可直接作为两个位置参数传入，不必手工转为 JSONL。

先跑 H001–H005 时，把 `--tasks` 指向 `evals/pt1-human-annotation-task-5-20261111.csv`；JSONL 中只放这五题的两人记录。

校验器比对 task ID、DOI、任务与清单 SHA、实际 PDF SHA、页码和精确原文 span。它检查最小证据声明及答案性字段的一致性，不替人判断问题在语义上是否可答，也不能证明证据集合确为最小。

标注者在问题、答案性、答案或证据集合上有分歧时，报告标 `pending_adjudication` 并列出冲突字段。校验器不平均答案、不合并引文、不猜最终结论。`ambiguous` 需先改写问题，再交仲裁。标注结构或来源校验失败时标 `invalid_annotations`；缺少两名不同标注者时标 `insufficient_independent_annotations`。无分歧只标 `agreement_pending_final_review`，不导出 gold；仍需按现有流程由复核者确认。报告不含答案、引文、PDF 路径或文本。

验证：PT-1 双人校验器、现有空白任务模板、CSV 导入器、单人 JSONL 校验器和最小标注包相关回归共 **28 passed**。只用临时合成 PDF 和现有空白模板校验；未读取 PT-1 真实 PDF、未填写真实 gold、未调用模型。双人标注身份仍需由项目流程确认。
