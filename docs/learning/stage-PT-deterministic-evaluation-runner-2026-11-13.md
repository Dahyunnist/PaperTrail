# PT 确定性检索评测运行器

## 本阶段问题

原有 `papertrail.evaluate` 可计算召回与证据覆盖，但缺少一个将冻结数据清单、gold 校验、运行元信息和报告输出绑定的公开 CLI。现在新增 `papertrail.evaluate_run`；它复用既有检索评测器，不引入第二套评分逻辑。

## 数据流

```text
source manifest + gold JSONL
        │  SHA-256、题数、gold schema 校验
        ▼
compare_modes(SQLite index, fixed k, named modes)
        │
        ├── evaluation：召回、MRR、nDCG、证据命中、逐题失败分类
        └── runtime：生成时间、Python/平台、耗时与按模式延迟
                    │
                    ▼
               JSON report
```

## 关键设计与取舍

- `--manifest` 必须声明数据来源类型、gold 路径和 SHA-256；gold 路径、字节哈希和可选 `question_count` 都与输入文件校验。题数始终来自通过 `load_gold` 的实际总题数，包含拒答题。
- `--minimum-questions` 默认 1，便于小型冻结诊断集；正式集应传项目要求的门槛。低门槛不代表样本足以支持泛化结论。
- 检索模式和 `k` 固定为命令参数。gold 指标与逐题 trace 放在 `evaluation`；壁钟耗时、执行时间、Python 和平台放在 `runtime`，避免把机器噪声混入检索质量指标。
- 报告只写数据集标签、哈希和聚合/逐题检索结果，不复制 source manifest 路径或文献全文。现阶段 source manifest 必须是公开、安全可提交的冻结清单。
- 入口不调用生成模型。它测检索，不测回答忠实度或端到端问答质量。
- 新报告附带 `run_manifest`，对齐四项目运行规范：绑定 Git、数据集/gold、split、评分器、运行/trace ID、预算、时间与状态。无模型评测使用 `model_id=none`、来源清单明确声明的 gold 来源、零成本；不适用的 prompt/tool/runtime 哈希与 token 预算写 `null`，不能伪造模型元数据。
- 额外记录 source manifest/gold SHA、来源类型、检索模式、`k`、总题数和报告指纹。manifest 在报告写盘前校验；无效身份、哈希、时间或模型边界都会拒绝输出。

## 失败路径

1. gold 被改动或清单哈希错误：在创建报告前失败，不留下看似有效的结果。
2. 清单题数与 gold 实际题数不同，或 gold schema 不合法：拒绝评测，避免运行结果与冻结集口径错位。
3. 数据库缺表、目标文档不在索引中或检索模式缺依赖：底层 evaluator 抛出错误；必须记录失败并修复环境，不能伪造零分报告。

## 复现命令

```powershell
.\.venv\Scripts\python.exe -m papertrail.evaluate_run `
  --db .local\papertrail.sqlite3 `
  --gold evals\pt17-heldout-gold-20261023.jsonl `
  --manifest evals\pt17-heldout-source-manifest-20261023.json `
  --report .local\pt17-retrieval-report.json `
  --k 5 --minimum-questions 5 --modes bm25 hybrid
```

本轮定向 pytest 为 **16 passed**（`test_evaluate_run.py`、`test_evaluate.py`、`test_run_manifest.py`）；`git diff --check` 通过。测试只运行临时合成 PDF fixture，没有读取 E 盘毕设论文或调用模型，也没有产出真实论文指标；不能外推为语料评测成绩。最近全量测试记录为 169 passed、1 项因测试宿主禁止绑定 loopback 被拦截；该环境限制不是应用断言通过。

## 用户亲手实验（10–20 分钟）

1. 先用 PT1 流程从临时合成 PDF 建索引；不要把 `.local` 索引提交 Git。
2. 复制合成 gold 和 manifest 到临时目录，运行上述 CLI，并检查 `provenance`、`evaluation`、`runtime` 三段。
3. 改动 gold 一个字节后重跑，确认 CLI 因 SHA 不匹配而在写报告前退出。
4. 把 manifest 的 `question_count` 改为错误值，确认入口拒绝运行；恢复临时文件后再试 BM25 与 hybrid。

## 面试追问

1. **为什么把延迟从指标里拆开？** 延迟受机器、缓存和负载影响；质量比较需固定检索模式与语料，运行环境另行记录，避免把测量噪声解释为相关性提升。
2. **哈希能证明 gold 正确吗？** 不能。哈希只证明评测读取的是冻结字节；问题和证据的正确性仍需人工标注和原文核验。
3. **小合成集能支持什么结论？** 只能回归已知边界、验证入口和诊断检索行为；不能证明真实论文覆盖或泛化能力。

## 结果与未完成项

- 新增 manifest 绑定的确定性 CLI 与合成 fixture 测试；核心评测逻辑复用 `compare_modes`。
- 真实来源的 gold 仍需人工标注、双人复核和冻结；本阶段没有读取私人 PDF、调用模型或声称完成真实文献评测。
