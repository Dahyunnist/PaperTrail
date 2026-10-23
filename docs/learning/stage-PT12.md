# PT12：冻结新论文隔离测试组

日期：2026-10-23

## 来源与冻结

PT12 新增三篇 PLOS Computational Biology 论文。官方出版者页面明确标示 Creative Commons Attribution License。来源页面、许可证据、发布日期、PDF 地址和本地 SHA-256 均登记于公共许可 registry 与 source manifest。

| 论文 | DOI | PDF 页数 | SHA-256 |
|---|---|---:|---|
| [Ten simple rules to cultivate transdisciplinary collaboration in data science](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1008879) | 10.1371/journal.pcbi.1008879 | 12 | `fb6cf1880a44b5c65c9925fc753f36a8032986e01f6ac4a22dd285cf39e1f292` |
| [Ten simple rules for navigating the computational aspect of an interdisciplinary PhD](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1008554) | 10.1371/journal.pcbi.1008554 | 12 | `af8b3122f5f85e877f423e7cff5fbeb4019593945c9c6ad21de56d03cc6f228e` |
| [Ten simple rules for building and maintaining a responsible data science workflow](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1012232) | 10.1371/journal.pcbi.1012232 | 19 | `f8e2af70e399923198b253109e255d3a818f732ce97dbd5092cf7c6accead567` |

冻结六道题：四道事实定位题、一题跨论文比较题和一道不可回答题。六条页级短证据均通过来源 SHA-256、PDF 物理页码与原文核验。黄金集 SHA-256 为 `d1ee0919a8bcddb3b040b573dc53b871f46e2dc54aa674d63d29d35d1d1ea01f`。

PT12 冻结时未暴露。冻结前没有创建检索索引，也没有运行检索、问答或生成模型。PT14 达标后，PT12 与 PT9 合并完成一次最终评测；结果未用于调参。两组评测后不再称为盲测。详见[最终 holdout 评测](final-public-holdout-evaluation-20261023.md)。

## 复现与冻结校验

```powershell
.\.venv\Scripts\python.exe scripts/fetch_pt5_public_group.py --group pt12-public-heldout-20261023 --expected-count 3 --manifest evals/pt12-heldout-source-manifest-20261023.json
.\.venv\Scripts\python.exe -m papertrail.gold --sources evals/pt12-heldout-sources.yaml --gold evals/pt12-heldout-gold-20261023.jsonl --minimum-questions 1
```

冻结 PT12 时，公开组累计 24 篇论文、42 道题；当时测试集仍未评测，距离 30 篇下限还差 6 篇。PT13/PT14 后达到目标，并完成一次最终合并评测。该阶段冻结数据未变。
