# PT-1 人工标注任务指南

## 任务包

- 任务表：`evals/pt1-human-annotation-task-40-20261111.csv`
- 来源清单：`evals/pt1-candidate-manifest-20261111.json`
- 离线生成器：`scripts/build_pt1_human_annotation_task.py`
- 表结构校验器：`scripts/validate_pt1_human_annotation_task.py`

任务表含40个候选问题，覆盖30个不同 DOI。每篇至少一个单篇问题；另有10个问题从10篇论文的第二个规则标题生成，用来探测文中是否报告对应的量化效果。候选问题由本地 PDF 标题/规则标题确定性生成，不含模型输出。`candidate_basis` 和 `candidate_basis_pdf_page` 只说明候选题从哪里提出；不是证据标注。

所有论文都属于 `development_seen`，来源并非盲集。候选题需要人工审核、必要时改写或删除。问题只能针对该行 DOI，不得拼接其他论文信息。

## 标注字段

复制原始 CSV 到单独工作副本，再填写。保留原始模板不变，以便校验和复现。

- `answerability`：填 `可答`、`不可答` 或 `歧义`。逐项检查问题中的每个要求。只有论文原文能直接支持全部要求，才标可答。缺少关键事实标不可答；问法有多种合理解释时先标歧义并改写。
- `expected_answer`：用简短答案响应候选题；不可答题填写明确的拒答依据，不猜测论文外事实。
- `minimal_complete_evidence_quote`：逐字抄录支撑答案所需的最小完整引文。若要多处证据，把引文写作 JSON 字符串数组。
- `evidence_pdf_pages`：填一基 PDF 物理页码；多处引文用 JSON 整数数组，顺序与引文一致。不要用页面印刷编号替代 PDF 物理页码。
- `original_pdf_excerpt`：逐字记录每处引文所在的原文上下文；多处用 JSON 字符串数组。保留符号、单位、否定词和小数点。
- `span_start_char`、`span_end_char`：按 PyMuPDF `page.get_text("text")` 原始页文本的 Unicode 字符索引填写，0 起点、右端不包含。多个引文在 `notes` 中以 JSON 数组记录对应 span；如解析文本无法稳定定位，留空并在备注说明，不能伪造。
- `annotator`、`reviewer`：填写真实参与者身份。标注者与复核者不能相同。
- `review_status`：复核前填 `未复核`；复核后填 `通过` 或 `退回`。退回时在 `notes` 写明具体问题。

不可答题的证据字段可以为空，但需标记为何无法从来源回答；引用用于证明“文中没有”的泛化说法不能替代对问题范围的复核。`歧义`题在进入冻结集前必须改写并重新标注。

## 抽样与冻结

任务表固定30篇 DOI、40题：30题按来源覆盖，10题是量化效果边界探测。所有题按 DOI 隔离。人工审阅时可替换不合格候选，但保持至少30篇不同 DOI、总计至少40题，并记录每次替换和理由。

冻结前逐题复核来源 DOI 与 PDF SHA-256、可答性、答案、最小完整证据集合、页码和原文摘录。每道题由第二人独立核对；退回题修订后再次复核。最终仅在两人确认后，把通过题写入 PT-1 gold JSONL，并更新 gold 哈希和清单版本。原始模板的所有标注字段必须继续为空。

## 运行校验

```powershell
.\.venv\Scripts\python.exe scripts/build_pt1_human_annotation_task.py
.\.venv\Scripts\python.exe scripts/validate_pt1_human_annotation_task.py
```

校验器要求40行、30个 DOI、字段结构匹配、来源哈希一致，且答案、可答性、引文、页码、摘录和复核字段全部留空。它校验模板，不校验人工填写后的副本。
