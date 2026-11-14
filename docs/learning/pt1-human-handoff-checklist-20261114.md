# PT-1 双人标注交接清单（2026-11-14）

本清单用于真实标注者开始工作。标注内容和导入产物留在用户本机，不提交到仓库，不上传到外部服务；PT-1 全部来源仍是 `development_seen`，不能称为盲测。

## 两位标注者各自领取

- 标注者 A：`evals/pt1-dual-annotation-40-20261112-a.csv`
- 标注者 B：`evals/pt1-dual-annotation-40-20261112-b.csv`
- 两人共同参考权威题目/来源登记：`evals/pt1-human-annotation-task-40-20261111.csv`、`evals/pt1-candidate-manifest-20261111.json` 和冻结分组 `evals/pt1-dual-annotation-40-20261112-frozen-grouped.json`。
- 每人须独立查看每题所列 DOI 对应的公开来源 PDF；用任务/manifest 中的 SHA-256 确认版本。A、B 不互看答案，不共用同一份填写副本。先复制工作表到本机 `.local/` 再填写，原始模板保持不变。

## 每题必填

`task_id`、唯一的 `annotator_id`、`independent=true`、原任务 DOI 与 `pdf_sha256`、最终 `question`、`question_type`、`answerability`、`expected_answer`（不可答时写拒答理由）、`minimum_complete_evidence_set=true`、`evidence`。

可答题的 `evidence` 是 JSON 数组；每条至少包含：

- `doi` 与 `pdf_sha256`
- 一基 PDF 物理页码 `pdf_page`
- 从该页 PyMuPDF 原生文本复制的 Unicode 半开字符区间 `start_char`、`end_char`
- 与该 span 完全逐字相同的 `quote`
- `relation`：`supports`、`contradicts` 或 `context`

证据集合必须覆盖答案每个必要事实，且人工确认其最小完整性。不可答题的 evidence 留空；有歧义的问题先改写或交仲裁，不得猜测或补引文。候选问题可被修订，但不能把候选依据当成答案证据。

## 校验与仲裁

1. 两人各自完成全部 40 题后，将两份副本放在本机 `.local/`。
2. 运行双人校验器：

   ```powershell
   .\.venv\Scripts\python.exe scripts\validate_pt1_dual_annotations.py .local\pt1-a-filled.csv .local\pt1-b-filled.csv --tasks evals\pt1-human-annotation-task-40-20261111.csv --manifest evals\pt1-candidate-manifest-20261111.json --report .local\pt1-adjudication-status.jsonl
   ```

3. 任何 `invalid_annotations` 或 `insufficient_independent_annotations` 先由原标注者修正；`pending_adjudication` 由项目指定的第三位裁决者对照来源逐题决定，并记录理由。即使两人一致，也要完成最终复核。校验报告只含题 ID、状态、冲突字段与标注者 ID，不含答案或引文。
4. 人工裁决后，由负责人整理一份最终 PT-1 v2 JSONL：`paper_ids` 为题目涉及 DOI，`split` 固定为 `development`；证据沿用上述 DOI/SHA/page/span/quote/relation 结构；`minimumCompleteEvidenceSet=true`、`annotation_status="human_verified"`，并记录最终标注者与不同的复核者。双人校验器不会自动合并或挑选答案；未裁决的 A/B 文件不能直接导入 gold。
5. 用冻结来源清单验证并导入 v2 JSONL：

   ```powershell
   .\.venv\Scripts\python.exe scripts\validate_pt1_gold_jsonl.py .local\pt1-adjudicated-v2.jsonl --min-questions 40 --min-papers 30
   .\.venv\Scripts\python.exe scripts\import_pt1_gold_jsonl.py .local\pt1-adjudicated-v2.jsonl --manifest evals\pt1-candidate-manifest-20261111.json --output-gold .local\pt1-runtime-gold.jsonl --output-sources .local\pt1-runtime-sources.yaml --min-questions 40 --min-papers 30
   ```

   v2 校验/导入会读取 manifest 所列公开 PDF 来验证当前 SHA、页码和逐字 span；只在人工文件到位且明确开始 gold 验收后运行。运行 gold 评测不是本清单的自动步骤。

## 目前仍需人工完成

两份独立 A/B CSV、独立作答声明、逐题原文证据定位、冲突裁决、最终 reviewer 复核及 v2 JSONL 整理均无法由工具代替。完成前 PT-1 仍为 0/40 gold；这 30 篇 DOI 与历史评测来源有重叠，整批始终只作已见开发数据，不得作为独立 holdout。
