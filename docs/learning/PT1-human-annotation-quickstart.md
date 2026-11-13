# PT-1 人工标注速查

本流程由两名真实标注者完成。仓库不生成答案或 gold；所有带论文摘录的文件只在用户本机使用，禁止上传、发给模型或粘贴到外部服务。

## 文件

- 40 题任务模板：`evals/pt1-human-annotation-task-40-20261111.csv`
- 来源与 SHA 清单：`evals/pt1-candidate-manifest-20261111.json`
- 双人独立填写表：`evals/pt1-dual-annotation-40-20261112-a.csv`、`evals/pt1-dual-annotation-40-20261112-b.csv`
- 冻结分组记录：`evals/pt1-dual-annotation-40-20261112-frozen-grouped.json`
- 导入器：`scripts/import_pt1_human_csv.py`
- 双人校验器：`scripts/validate_pt1_dual_annotations.py`

## 分工与填写

两人各自独立填写 A、B 表的全部 40 题，不互看答案后再提交。每题填写 `task_id`、`annotator_id`、`independent=true`、`doi`、`pdf_sha256`、`question`、`question_type`、`answerability`、`expected_answer`、`minimum_complete_evidence_set=true`、`evidence`。题目、DOI 和 SHA 必须对应任务行；标注者 ID 必须不同。

只有原文支持问题全部必要要点时填 `answerable`，否则根据原文缺失或证据不足填 `unanswerable`；问法有多种合理解释时先标 `ambiguous`，暂停该题并提交裁决，不得导入 gold。答案须简洁且有证据；不可答题写明拒答理由，`evidence` 留空。

可答题的 `evidence` 是最小完整集合：覆盖答案每个必要事实，删掉任一条就会有事实失去支持。每条记录含 `doi`、`pdf_sha256`、一基物理页码 `pdf_page`、原始页文本 Unicode 左闭右开区间 `start_char`/`end_char`、逐字 `quote` 和 `relation`（`supports`/`contradicts`/`context`）。不得用印刷页码替代 PDF 页码，也不得猜测 span。无证据时标注 pending，不补造 gold。

两表均完成后运行双人校验。冲突或任一题未满两份有效独立标注时，状态保持 pending；由用户指定第三位裁决者对照原文逐题裁决，记录理由，再重跑校验。脚本只报告分歧，不自动选答案。

## 命令

在仓库根目录执行。先校验冻结任务清单：

```powershell
.\.venv\Scripts\python.exe scripts\export_pt1_dual_annotation_tasks.py validate evals\pt1-dual-annotation-40-20261112-frozen-grouped.json --tasks evals\pt1-human-annotation-task-40-20261111.csv --manifest evals\pt1-candidate-manifest-20261111.json
```

校验两份本机填写表并输出报告：

```powershell
.\.venv\Scripts\python.exe scripts\validate_pt1_dual_annotations.py evals\pt1-dual-annotation-40-20261112-a.csv evals\pt1-dual-annotation-40-20261112-b.csv --report .local\pt1-dual-review.json
```

仅在所有题通过独立标注、分歧裁决后，把一份已裁决 CSV 导入；`--manifest` 指向官方冻结来源清单：

```powershell
.\.venv\Scripts\python.exe scripts\import_pt1_human_csv.py .local\pt1-human-annotation-adjudicated.csv --manifest evals\pt1-candidate-manifest-20261111.json --output-v2 .local\pt1-human-v2.jsonl --output-gold .local\pt1-runtime-gold.jsonl --output-sources .local\pt1-runtime-sources.yaml --min-questions 40 --min-papers 30
```

导入器会核对每条证据的 PDF SHA、物理页、逐字引文和字符 span；任一无效则失败，不发布 gold。真实标注和导入产物留在本机 `.local/`，不得提交仓库。

PT-1 当前仍为 0/40 人工 gold；完成上述人工步骤前不得报告真实评测结果。
