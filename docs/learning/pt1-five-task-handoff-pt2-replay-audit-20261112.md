# PT1 五题标注交接与 PT2/P9 重放审计（2026-11-12）

## PT1 五题交接

`evals/pt1-human-annotation-package-5-20261112.json` 从 5 行候选 CSV 与来源元数据生成，只含任务 ID、SHA 派生的相对来源 ID、PDF SHA、候选问题和待人工填写字段。没有保存实际文件路径、DOI、PDF 文本或引文。全部 gold 字段保持空值；任务包不是已完成 gold。

本机 PDF 未打开。因而不能提供或推断短引文、真实证据页、答案或字符范围。候选问题和 SHA 锁定标注对象；标注者需在本地原 PDF 找到最短完整证据并填写字段，第二位复核者独立核对。

只检查任务包结构、不打开 PDF：

```powershell
.\.venv\Scripts\python.exe scripts/validate_pt1_minimal_annotation_package.py evals/pt1-human-annotation-package-5-20261112.json
```

人工与复核完成后，再用既有完整导入器校验真实 SHA、页码、span 和来源原文。该命令会读取 PDF，须由标注者在授权本机环境执行：

```powershell
.\.venv\Scripts\python.exe scripts/import_pt1_human_csv.py evals/pt1-human-annotation-task-5-20261111.csv --min-questions 5 --min-papers 5 --output-v2 .local/pt1-human-gold-v2.jsonl --output-gold .local/pt1-human-gold-runtime.jsonl --output-sources .local/pt1-human-sources.yaml
```

截至本审计，原 CSV 仍为 0/5 已标注、0/5 已复核。任务包不能解除人工 gold 关口。

## PT2/P9 历史结果能否重放

PT2 synthetic 3×3 结果与真实论文结果分开。历史 **5/27** 属于 P9 真实论文 development run，不是 PT2 合成小集，不是新评测，也未在本轮重放。P9 记录 27 道可答题中 5 道作答、22 道错误拒答；3 道不可答题正确拒答。5 个作答经历史人工复核为 4 正确、1 部分正确、0 错误。

错误拒答细分：1 次证据组织失败；21 次发生在生成/审查，其中 16 次输出空 claims、5 次达到输出长度限制。该数字来自既有 P9 学习记录；缺少可在此处独立复算的逐题安全 trace，不能当作本轮重新分类结果。

完整 QA run 不能由已提交工件重放：历史语料和 SQLite 检索库为本机数据，BGE 索引/模型资产不是此审计的冻结输入；历史 5/27 又依赖模型生成。共享费用门禁仍关闭。本轮只复核已提交的 `docs/learning/stage-P9.md` 汇总，不读取 `.local`、PDF、来源 manifest、回答全文或 `.env`。机器可读边界和计数见 `evals/pt2-real-replay-audit-20261112.json`。

结论只报告历史开发结果和当前不可复放原因，不声称模型或真实 PDF 质量改善。
