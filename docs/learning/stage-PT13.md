# PT13：公共数据与研究社群开发诊断集

日期：2026-10-23

## 来源与冻结

PT13 新增三篇 PLOS Computational Biology 论文。出版者页面标示 Creative Commons Attribution License。来源版本、官方 PDF、本地 SHA-256 与许可页见 registry 和 source manifest。

| 论文 | DOI | PDF 页数 | SHA-256 |
|---|---|---:|---|
| [Ten simple rules for humane data science](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1011698) | 10.1371/journal.pcbi.1011698 | 7 | `34466c3a60a651172a015a948148b063e627ab288438d0b4897241d3515dd303` |
| [Ten simple rules for improving research data discovery](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1009768) | 10.1371/journal.pcbi.1009768 | 11 | `7bc4ddf60ed24be41d5b3337de2a4c1294a8295e1f2ecc798806326c36e3cde8` |
| [Ten simple rules for creating a global network in computational biology](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1010528) | 10.1371/journal.pcbi.1010528 | 11 | `22a5065918ae639b88a4bfb58e3b634c98f406340fc199448feacea6c992f1ed` |

冻结四道题：三道事实定位题、一题跨论文题。五条页级短证据通过来源哈希、物理页码和原文核验。黄金集 SHA-256 为 `e74729376879b3465497f93f1ee38c3e89d39820c4c37a82409b16c1f27fcaf7`。

## 离线检索与证据路径

索引含 29 个 PDF 页、394 个文本块，解析器为 `papertrail-s1-4`。Dense BGE 未运行：环境缺少 `sentence_transformers` 与 `torch`。未调用生成模型或 API。

| 模式 | Recall@5 | MRR@5 | 全目标页@5 | 完整证据@5 | Recall@10 | MRR@10 | 全目标页@10 | 完整证据@10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BM25 | 0.750 | 0.750 | 0.750 | 0.750 | 1.000 | 0.781 | 0.750 | 0.750 |
| 字符 TF-IDF + SVD | 1.000 | 1.000 | 0.750 | 0.750 | 1.000 | 1.000 | 0.750 | 0.750 |
| BM25 + 向量 RRF | 0.750 | 0.750 | 0.750 | 0.750 | 1.000 | 0.778 | 0.750 | 0.750 |

三种模式在 k=10 均找到四题的至少一个黄金页，但只有三题覆盖全部证据。跨论文问题是完整证据缺口。按题型区分，单篇事实题检索更稳定。

四道可回答题均返回 `verified_excerpts`，模型名为空。最终 QA 引用覆盖 3/5 条黄金页，完全匹配的黄金短引文为 0/5。检索命中不保证最终引用呈现完整，也不保证引文截取边界与黄金短引文相同。

## 复现

```powershell
.\.venv\Scripts\python.exe scripts/fetch_pt5_public_group.py --group pt13-public-development-20261023 --expected-count 3 --manifest evals/pt13-public-source-manifest-20261023.json
.\.venv\Scripts\python.exe -m papertrail.gold --sources evals/pt13-development-sources.yaml --gold evals/pt13-development-gold-20261023.jsonl --minimum-questions 1
.\.venv\Scripts\python.exe -m papertrail index --sources evals/pt13-development-sources.yaml --selection .local/pt13-development-selection.jsonl --db .local/pt13-development.sqlite3
.\.venv\Scripts\python.exe -m papertrail vector-build --db .local/pt13-development.sqlite3 --artifact .local/pt13-development.vectors.joblib
.\.venv\Scripts\python.exe -m papertrail.evaluate --compare --db .local/pt13-development.sqlite3 --gold evals/pt13-development-gold-20261023.jsonl --k 10 --minimum-questions 1 --modes bm25 vector hybrid --vector-artifact .local/pt13-development.vectors.joblib
```

PT13 后公开组累计 27 篇论文、46 道题。PT9 与 PT12 的六篇测试论文、12 道题仍未评测。
