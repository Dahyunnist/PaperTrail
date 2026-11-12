# PT1 40 题工作流与 PT2 重放边界（2026-11-12）

## 标注包与材料充足性

已有 40 行候选 CSV 覆盖 30 个不同 DOI；候选任务字段齐全，满足启动 40 题人工工作流的数量条件。它们仍是待人工核对的候选，不等于 40 个合格 gold 问题。零标注、零答案、零引文、零证据页、零双人通过状态。此阶段不读取 PDF，不补造任何答案、引文或页码。

新增 40 项包 `evals/pt1-human-annotation-package-40-20261112.json`，只含任务 ID、PDF SHA、SHA 派生相对来源 ID、候选问题和空白人工字段；不含路径、DOI、PDF 文本或 gold。5 项 pilot 仍见 `evals/pt1-human-annotation-package-5-20261112.json`，对应 `PT1-H001`–`PT1-H005`。

原有导入器已有字段、证据页、原文上下文、span、两名不同人员和 `通过` 状态校验；CSV→v2 JSONL→运行时 gold 的导入流程已存在。本轮把分歧流转明确为 `待复核`、`退回修改`、`分歧待仲裁`、`通过`。仅 `通过` 状态允许导入。更详细步骤见 [人工标注指南](pt1-human-annotation-guide-20261111.md)。

只校验模板/任务包，不读 PDF：

```powershell
.\.venv\Scripts\python.exe scripts/validate_pt1_human_annotation_task.py
.\.venv\Scripts\python.exe scripts/validate_pt1_minimal_annotation_package.py evals/pt1-human-annotation-package-40-20261112.json
```

导入只在人工填写并双人复核后运行。导入器会读取 PDF 来验证真实页码、SHA 和 span：

```powershell
.\.venv\Scripts\python.exe scripts/import_pt1_human_csv.py <已复核40题CSV副本路径> --manifest evals/pt1-candidate-manifest-20261111.json --output-v2 .local/pt1-human-gold-v2.jsonl --output-gold .local/pt1-human-gold-runtime.jsonl --output-sources .local/pt1-human-sources.yaml
```

测试确认空 gold 会被 `load_gold` 拒绝，不会作为可评测数据。PT1 gold 仍为 0/40。

## PT2/P9 真实论文重放

`scripts/evaluate_pt1_local.py` 是离线检索评测入口，默认依赖 `.local/pt1-real-dev-gold.jsonl`、`.local/pt1-real-dev-manifest.json`、`.local/papertrail-expanded-s1.sqlite3`、向量制品和配置来源。脚本先校验 gold SHA，再调用 `verify_quotes` 逐条读取原 PDF。因此命令虽不调用模型，却不能在不访问本机语料、索引和 PDF 时复跑真实论文分数；本轮未运行，也未验证这些本地输入是否齐全。

`docs/learning/stage-PT2.md` 的真实集历史结果为 8 题：BM25 完整引文集合 4/8、字符向量 1/8、RRF 4/8。页命中不等于完整证据。P9 历史 QA 的 5/27 及拒答分类属于另一套真实 development run，不是 PT2 检索分数，也未重放。既有复核为 22/27 可答题错误拒答：1 次证据组织失败；21 次生成/审查失败，其中 16 次空 claims、5 次长度限制。此为旧报告汇总，不构成本轮样本级复核或质量改善证据。

模型 QA 无法从已提交工件离线重放：需要历史本机索引、BGE/向量资产和原模型生成条件；共享预算门禁仍关闭。只审计命令与文档，没有读取 `.local`、来源 manifest、PDF、回答全文或 `.env`。
