# PT2 无标签重放入口与 PT3 引文失败路径（2026-11-12）

## PT2 输入与当前状态

新增 `scripts/audit_pt2_unlabeled_retrieval.py`。它只接受显式来源配置、选择清单、BM25 查询 JSONL、独立 SQLite 路径和输出路径；先按选定 manifest 重建/对账索引，再输出 top-k 文档 SHA、页码、chunk ID 和分数。报告仅保存输入文件 SHA、索引版本、查询 ID/hash、候选数和排序；不保存查询正文、文档标题/全文、本机路径或答案。它不读取 `.env`、不调用模型、不需要 gold。

无 gold 时只做候选审计，`gold_metrics=null`。不得把命中数量当 Recall、完整证据覆盖或答题质量。待用户提供明确授权的本地来源配置和 selection 清单后，可在本机执行：

```powershell
.\.venv\Scripts\python.exe scripts/audit_pt2_unlabeled_retrieval.py --database .local/pt2-authorized.sqlite3 --sources <本地授权来源配置.yaml> --selection <冻结选择清单.jsonl> --queries <不含答案的查询集.jsonl> --output .local/pt2-unlabeled-audit.json --limit 10
```

本轮另加可重复的 synthetic-only 定位回放：测试临时造一份两页 PDF，目标词只在第 2 页出现；在两个新 SQLite 索引上分别跑固定 BM25 查询，比较命中列表，并用来源 SHA、物理页和精确 span 验证目标引文。报告仍不含 query 正文、原文或路径；不计算 gold 指标，也不代表真实文献质量。

真实 PT2 旧脚本 `scripts/evaluate_pt1_local.py` 需要 `.local/pt1-real-dev-gold.jsonl`、`.local/pt1-real-dev-manifest.json`、`.local/papertrail-expanded-s1.sqlite3`、向量文件和来源配置；还会逐题验证 gold 引文并打开 PDF。因此本轮没有运行。此前文档记录的 8 题完整证据覆盖为 BM25 4/8、向量 1/8、RRF 4/8；失败为 PT1-02 至 PT1-05 的至少一个必要证据缺失。该数值是历史结果，没有本轮复现。

要计算可答题 Recall 或完整证据集合率，用户还需提供逐题冻结 gold：问题、question ID、每条必需引文的来源 SHA、物理页和精确短引文；gold 必须由人工核对。没有它时保留 unlabeled 状态。

## PT3 引文负例审计

`papertrail.qa._validate_quote` 要求引用文本经规范化后存在于指定 PDF SHA 所指向的文件、指定物理页。既有测试已覆盖错误哈希、越界页码、错误引文和 OCR 派生证据拒绝。本轮新增跨来源替换反例：两份合成 PDF 有相同短引文，把来源 A 的 SHA 配到来源 B 路径仍须失败。

限制：QA runtime citation 保存文件路径、SHA、页码和精确 quote，不保存 quote 字符偏移；导入 gold 流程则额外核验字符 span。新反例证明路径与 SHA 绑定，不证明所有 OCR、PDF 重排或多页证据都能完整捕获。

## 验证

`tests/test_pt2_unlabeled_audit.py` 与 `tests/test_pt3_citation_failure_paths.py` 使用运行时生成的合成 PDF：

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .tmp/pytest-pt2pt3 tests/test_pt2_unlabeled_audit.py tests/test_pt3_citation_failure_paths.py
```

无标签回归检查结果不含 query 原文、PDF 文本和本机路径；整个验证没有读取私人来源或调用模型。

## PT-3 部分覆盖回归复核（2026-11-13）

tests/test_s3.py::test_complex_ask_retrieves_each_subquestion_and_keeps_partial_answer 验证保留已支持结论并报告 missing 子问题；	ests/test_s3.py::test_qa_preserves_supported_partial_answer_and_logs_reason 验证 API/历史状态为 generated_partial，而非完整或整体拒答。两项通过。行为由 fake generator 驱动，不调用模型；未改 gold。真实 PT-3 人工 gold 仍待标注。

