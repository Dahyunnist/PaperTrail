# PT11：新增计算笔记本与同行评审开发集

日期：2026-10-23

## 来源与冻结

PT11 新增三篇 PLOS Computational Biology 论文。官方页面明确标示 Creative Commons Attribution License，官方 PDF、本地 SHA-256、许可证据与版本记录见公共许可 registry 和 PT11 source manifest。

| 论文 | DOI | PDF 页数 | SHA-256 |
|---|---|---:|---|
| [A simple kit to use computational notebooks for more openness, reproducibility, and productivity in research](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1010356) | 10.1371/journal.pcbi.1010356 | 12 | `3e88c105c0292a07c3dcc32872c6f2acfe865173aebd757dded9874b0ae2dc2a` |
| [Ten simple rules for writing and sharing computational analyses in Jupyter Notebooks](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1007007) | 10.1371/journal.pcbi.1007007 | 8 | `30af1629e0fe31b51a82c8f01c901a0ecc6d13bb61bc601861aeb3d260397910` |
| [Ten simple rules for writing a response to reviewers](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005730) | 10.1371/journal.pcbi.1005730 | 4 | `7a9dca63168f30698b05742a99f61d5b3b87cf33a01e374b702c8fc22dbfbfbf` |

冻结四道题：三道事实定位题和一道跨论文比较题。五条页级证据通过来源哈希、物理页码和原文核验。黄金集 SHA-256 为 `6a5808b12a021d8ee382a9d035fe846ed9ab5f99451281985919222cd06d49b7`。PT11 是开发诊断组。

## 离线检索与证据路径

索引包含 24 个 PDF 页、259 个文本块，解析器为 `papertrail-s1-4`。Dense BGE 未运行：当前环境缺少 `sentence_transformers` 和 `torch`。没有调用模型或 API。

| 模式 | Recall@5 | MRR@5 | 全目标页@5 | 完整证据@5 | Recall@10 | MRR@10 | 全目标页@10 | 完整证据@10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BM25 | 1.000 | 0.708 | 0.750 | 0.750 | 1.000 | 0.708 | 1.000 | 0.750 |
| 字符 TF-IDF + SVD | 1.000 | 0.550 | 0.750 | 0.750 | 1.000 | 0.550 | 0.750 | 0.750 |
| BM25 + 向量 RRF | 1.000 | 0.875 | 0.750 | 0.750 | 1.000 | 0.875 | 1.000 | 0.750 |

全部五条证据中，k=10 检索完整覆盖四条；遗漏的是计算笔记本 kit 与 Jupyter 规则之间跨论文题的 Jupyter 侧证据。三篇文章均有题目页命中，但完整证据覆盖只有 3/4 题。

五条目标证据再走 QA 最终摘录路径：四题均返回 `verified_excerpts`、模型名为空；最终引用覆盖 3/5 条黄金页和 1/5 条精确短引文。检索页 Recall 完美不代表最终引用证据完整。

## 复现

```powershell
.\.venv\Scripts\python.exe -m papertrail.gold --sources evals/pt11-development-sources.yaml --gold evals/pt11-development-gold-20261023.jsonl --minimum-questions 1
.\.venv\Scripts\python.exe -m papertrail index --sources evals/pt11-development-sources.yaml --selection .local/pt11-development-selection.jsonl --db .local/pt11-development.sqlite3
.\.venv\Scripts\python.exe -m papertrail vector-build --db .local/pt11-development.sqlite3 --artifact .local/pt11-development.vectors.joblib
.\.venv\Scripts\python.exe -m papertrail.evaluate --compare --db .local/pt11-development.sqlite3 --gold evals/pt11-development-gold-20261023.jsonl --k 10 --minimum-questions 1 --modes bm25 vector hybrid --vector-artifact .local/pt11-development.vectors.joblib --trace-out .local/pt11-development-retrieval-k10.json
```

PT11 后公开组累计 21 篇论文、36 道题，仍有三篇论文、至少四道题才能达到原规模下限。PT9 冻结测试组未在本阶段评测。
