# PT14：可复现研究、SOP 与可发现性开发诊断集

日期：2026-10-23

## 来源与冻结

PT14 新增三篇 PLOS Computational Biology 论文。官方页面标示 Creative Commons Attribution License。来源版本、官方 PDF、本地 SHA-256 与许可页见公共 registry 和 source manifest。

| 论文 | DOI | PDF 页数 | SHA-256 |
|---|---|---:|---|
| [Ten Simple Rules for Reproducible Computational Research](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1003285) | 10.1371/journal.pcbi.1003285 | 4 | `35648a3880bdd8bf30e8212a3847b7bd35f504ee5ccbd1ad3856d206acd181db` |
| [Ten simple rules on how to write a standard operating procedure](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1008095) | 10.1371/journal.pcbi.1008095 | 10 | `9b75c0de267d149fc598bd4cc960e9bb4ef388e4795afb0a4365825b4436e21b` |
| [Ten quick tips for making things findable](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1008469) | 10.1371/journal.pcbi.1008469 | 10 | `4828b5f780bfc00f0d62aff0d45c3cdd366023dd83858682486dcf3827382877` |

冻结四道题：三道事实定位题、一题跨论文比较题。六条页级短证据通过来源 SHA-256、物理页码和原文核验。黄金集 SHA-256 为 `dbe99316c71830fc530ac5b48b2064b1370aab56b13bee68d38d636d6ad87a7a`。

## 离线检索与证据路径

索引含 24 个 PDF 页、364 个文本块，解析器为 `papertrail-s1-4`。Dense BGE 未运行：环境缺少 `sentence_transformers` 与 `torch`。未调用生成模型或 API。

| 模式 | Recall@5 | MRR@5 | 全目标页@5 | 完整证据@5 | Recall@10 | MRR@10 | 全目标页@10 | 完整证据@10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BM25 | 0.750 | 0.583 | 0.750 | 0.750 | 0.750 | 0.583 | 0.750 | 0.750 |
| 字符 TF-IDF + SVD | 0.750 | 0.550 | 0.750 | 0.750 | 1.000 | 0.578 | 0.750 | 0.750 |
| BM25 + 向量 RRF | 0.750 | 0.583 | 0.750 | 0.750 | 0.750 | 0.583 | 0.750 | 0.750 |

k=10 时，只有向量检索在四题均命中至少一个黄金页，但完整证据覆盖仍是 3/4。增加候选数没有补齐跨论文题的全部证据。

四道可回答题均返回 `verified_excerpts`，模型名为空。QA 最终引用覆盖 2/3 条黄金页，逐字匹配黄金短引文为 0/5。页级命中与最终引用完整性仍有差距。

## 复现

```powershell
.\.venv\Scripts\python.exe scripts/fetch_pt5_public_group.py --group pt14-public-development-20261023 --expected-count 3 --manifest evals/pt14-public-source-manifest-20261023.json
.\.venv\Scripts\python.exe -m papertrail.gold --sources evals/pt14-development-sources.yaml --gold evals/pt14-development-gold-20261023.jsonl --minimum-questions 1
.\.venv\Scripts\python.exe -m papertrail index --sources evals/pt14-development-sources.yaml --selection .local/pt14-development-selection.jsonl --db .local/pt14-development.sqlite3
.\.venv\Scripts\python.exe -m papertrail vector-build --db .local/pt14-development.sqlite3 --artifact .local/pt14-development.vectors.joblib
.\.venv\Scripts\python.exe -m papertrail.evaluate --compare --db .local/pt14-development.sqlite3 --gold evals/pt14-development-gold-20261023.jsonl --k 10 --minimum-questions 1 --modes bm25 vector hybrid --vector-artifact .local/pt14-development.vectors.joblib
```

PT14 阶段结束时，公开组达到 30 篇论文、50 道题；PT9 与 PT12 共 6 篇测试论文、12 道题尚未评测。随后按计划完成一次合并评测，结果见[最终 holdout 评测](final-public-holdout-evaluation-20261023.md)。测试结果未用于调参。
