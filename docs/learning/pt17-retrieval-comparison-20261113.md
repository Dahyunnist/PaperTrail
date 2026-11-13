# PT17 检索模式对照

## 目的与范围

本次对照复用登记的 PT17 公共 CC BY 4.0 论文和冻结 gold，比较 BM25、字符向量和 RRF 混合检索在 `k=5`、`k=10` 时的证据覆盖。共 5 道题，其中 4 道可答、1 道不可答。它是小样本诊断，不是调参集、盲测新集或泛化结论。

## 数据流与复现

`scripts/evaluate_pt17_retrieval_comparison.py` 先校验源清单和 gold 哈希，再校验每个 PDF 位于登记的 `evals/fixtures/pt17-heldout/` 且 SHA-256 与清单一致。之后在忽略的 `.tmp/` 下建立一次性索引，调用现有 `run_evaluation` 两次：一次 `k=5`，一次 `k=10`，每次比较三个确定性检索模式。全程不生成回答、不调用模型，估算费用为 `$0`。

输出 `reports/pt17-retrieval-comparison-20261113.json` 包含每次评测的完整 schema-v1 run manifest 和报告指纹，以及逐题检索轨迹。运行器拒绝有已跟踪代码改动的工作区，保证 manifest 的 `git_sha` 指向实际运行的提交。外层报告同时记录 runner 源码 SHA、gold SHA、来源清单 SHA 和 commit SHA。报告不保存 PDF 全文、chunk 原文或本机绝对路径。

## 指标与边界

主要指标为 page Recall@k、完整证据集合覆盖率、nDCG 和平均查询时间。`complete_evidence_at_k` 要求一道题所需的全部 gold 页都被召回；普通 page hit 不能替代完整证据覆盖。单次均值包含首次索引/模型加载影响，不应当作稳定服务时延或 p95。

评测结果和逐题失败样本见 JSON 报告。PT17 gold 的人工来源标注仍为 `unspecified`；文件 hash 校验可证明输入一致，不能替代人工标注复核。5 题样本不能支持显著性或泛化结论。任何后续检索参数调整都必须另建开发集，并重新冻结评估集。

## 本次结果

| 模式 | k | Page Recall@k | 完整证据覆盖 | 平均查询时间（ms） |
|---|---:|---:|---:|---:|
| BM25 | 5 | 0.750 | 0.500 | 3.9 |
| Vector | 5 | 0.750 | 0.750 | 1,753.2 |
| Hybrid | 5 | 0.750 | 0.250 | 83.8 |
| BM25 | 10 | 0.750 | 0.500 | 28.7 |
| Vector | 10 | 0.750 | 0.750 | 53.2 |
| Hybrid | 10 | 0.750 | 0.500 | 82.5 |

该运行中 Vector 的完整证据覆盖最高，但只有 5 题，首轮均值受冷启动影响；不能据此替换默认模式。报告 SHA-256：`a2cd90ae508adcd60eaf61699da1afc77252e942b7399b96c197e29fa6a04b58`。k=5、k=10 两个嵌套 run manifest 均通过 schema-v1 校验，并分别保留各自报告指纹。

## 测试命令

```powershell
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_pt17_retrieval_comparison.py
.venv\Scripts\python.exe scripts/evaluate_pt17_retrieval_comparison.py
```

本次运行：4 项结构/边界测试通过；6 组检索运行完成，模型调用为 0。

## 设计取舍

- 复用已验证的索引构建器和 `run_evaluation`，避免复制 gold 读取、引文评分和 manifest 逻辑。
- 每个 k 保存完整底层评测对象，避免汇总文件丢掉 per-run manifest 或使指纹脱离其结果。
- 不把 6 组对照的单一最好分数变成默认检索，也不把 5 题分数表述成质量提升证明。

## 亲手实验

先在干净提交上运行脚本。检查报告里两份 manifest 的 `k`、三个 `retrieval_modes`、`model_id=none`、`cost_usd_estimate=0` 和 `report_fingerprint`。然后只改变输出路径重跑，核对 gold/source SHA 不变、运行时间戳与 run ID 更新。不要改 frozen gold、在同一集上调参后再称其 holdout。

## 面试追问

1. 为什么 page Recall@k 不足以描述跨页问题？因为答案可能需要多个 gold 页，必须同时测完整证据集合覆盖。
2. 为什么向量模式首轮均值明显慢时不能直接当线上 p95？它包含冷启动和索引构建，不是并发服务延迟分布。
3. 5 道题能否说明向量检索更好？不能。只能描述这 5 题和当前数据/配置下观察到的差异，且不能在此集上调参。
