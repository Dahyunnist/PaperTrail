# PT9：冻结新的论文隔离 holdout

日期：2026-10-23

## 数据与冻结

PT9 新增三篇 PLOS Computational Biology 文章，来源论文未进入 PT5–PT8 开发诊断组，也未用于 PT6 首测。PLOS 官方文章页面明确标注 Creative Commons Attribution License；出版日期、官方 PDF 地址、许可页和 CC BY 4.0 法律文本见 `configs/public-paper-license-registry.json` 与 `evals/pt9-heldout-source-manifest-20261023.json`。

| 论文 | DOI | PDF 页数 | SHA-256 |
|---|---|---:|---|
| [Ten Simple Rules for Effective Statistical Practice](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1004961) | 10.1371/journal.pcbi.1004961 | 8 | `527fc8f7054f80b2a2fd277afb9a1ea7ada2f96659140764729adf12a78d00ad` |
| [Ten simple rules for getting started with statistics in graduate school](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1010033) | 10.1371/journal.pcbi.1010033 | 9 | `53e867793aa1f3a710004ee3c10346b4c1b8e2e5fdf9abfdf700ec3d3e09cbb1` |
| [Ten simple rules for large-scale data processing](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1009757) | 10.1371/journal.pcbi.1009757 | 7 | `2f0758d577a8d09dbf45dc0c370ab303a2978858e0e2c0a0b979755c39f308bc` |

黄金集共六题：三道事实定位题、一题跨论文比较、一题两步流程题和一道不可回答题。七条短证据均通过来源 SHA-256、物理页码和 PDF 页文本核验。黄金集 SHA-256 为 `efe19dd142381ad36e36d928e37c0bfa4292c2423faacdb5e230054961160c39`。

PT9 冻结后一直未运行检索器、QA 或生成模型，也未据此选择算法或调参。PT14 达到公开语料目标规模后，PT9 与 PT12 合并进行了一次最终评测。评测后不得将两组继续称为盲测；评测结果没有用于后续调参。详情见[最终 holdout 评测](final-public-holdout-evaluation-20261023.md)。

本阶段只做来源许可核验、官方 PDF 下载与 SHA 检查、物理页文本查阅和人工黄金题核验。未创建检索索引或运行模型，不产生 API 费用。

## 复现来源和黄金校验

```powershell
.\.venv\Scripts\python.exe scripts/fetch_pt5_public_group.py --group pt9-public-heldout-20261023 --expected-count 3 --manifest evals/pt9-heldout-source-manifest-20261023.json
.\.venv\Scripts\python.exe -m papertrail.gold --sources evals/pt9-heldout-sources.yaml --gold evals/pt9-heldout-gold-20261023.jsonl --minimum-questions 1
```

PT9 冻结时公开语料累计 15 篇论文、28 道题，低于 PT1 原定规模。该历史阶段记录保留冻结时状态。PT9 后续已参加一次与 PT12 的合并评测；完整指标和局限见最终评测报告。PT6 首轮 holdout 与 PT9/PT12 最终测试保持区分。
