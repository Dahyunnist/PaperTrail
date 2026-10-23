# PT8：新增三篇公开许可开发论文

日期：2026-10-23

## 语料与冻结

本阶段新增三篇 PLOS Computational Biology 论文。出版者页面分别明确显示 Creative Commons Attribution License，下载仅使用官方 PLOS PDF 端点。记录页、许可证据页、CC BY 4.0 法律文本、版本日期、官方 PDF URL 和本地 SHA-256 见 `configs/public-paper-license-registry.json` 及 `evals/pt8-public-source-manifest-20261023.json`。

| 论文 | DOI | PDF 页数 | SHA-256 |
|---|---|---:|---|
| [Ten simple rules for using public biological data for your research](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1010749) | 10.1371/journal.pcbi.1010749 | 14 | `91f24205d15596227407fc5ade92c71d37c86dd1fc589b8dc1d64d7c7dd38ed0` |
| [Ten simple rules to host an inclusive conference](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1010164) | 10.1371/journal.pcbi.1010164 | 13 | `98d6d1458eac6b88fc8f8fd8e376ad1707e053f205db2b71e4a35ecdc2f09f4e` |
| [Ten simple rules for open human health research](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1007846) | 10.1371/journal.pcbi.1007846 | 18 | `67cdeb70bbb0697da49ef359b2cce9ac2edd78e5e7b3d294d563e552df61631e` |

PT8 与 PT5、PT6、PT7 来源论文互斥。冻结四道英文题：三道事实定位题和一道不可回答题。三条正向题的三条短证据均通过 SHA、物理页与原文校验。黄金集 SHA-256 为 `9a4aa48523bf01f9fb12b9a514ebeffc41f69f49cf583c768f59f695834c30dd`。PT8 归为开发诊断组，不用于独立测试。

## 离线检索结果

索引包含三篇论文、45 个 PDF 页、587 个索引块，解析器为 `papertrail-s1-4`。Dense BGE 未运行：锁定环境缺少 `sentence_transformers` 和 `torch`，本阶段没有下载运行依赖，也没有模型或 API 调用。`vector` 指字符 TF-IDF + SVD。

Recall@k 按至少命中一个目标物理页的问题计算；MRR 按目标物理页的排名计算；完整证据覆盖要求所有黄金页均被命中，且所有黄金短引文均出现在相应检索页文本中。

| 模式 | Recall@5 | MRR@5 | 全部目标页@5 | 完整引文@5 | Recall@10 | MRR@10 | 全部目标页@10 | 完整引文@10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BM25 | 0.667 | 0.500 | 0.667 | 0.667 | 0.667 | 0.500 | 0.667 | 0.667 |
| 字符 TF-IDF + SVD | 1.000 | 0.733 | 1.000 | 1.000 | 1.000 | 0.733 | 1.000 | 1.000 |
| BM25 + 向量 RRF | 0.667 | 0.667 | 0.667 | 0.667 | 0.667 | 0.667 | 0.667 | 0.667 |

三篇题目各自只含一条证据。BM25 和 RRF 均在“open human health research”题上找到目标文档但未命中目标物理页；向量模式三题全覆盖。不可回答题三种检索模式都返回候选，不能据此判断最终拒答是否正确。

## 最终引用页路径

使用 `ask(..., generate=False)` 对三道可回答题运行实际引用路径。三题均返回 `verified_excerpts`，模型名为空。最终显示摘录覆盖 1/3 条黄金物理页，精确黄金短引文覆盖 0/3。该结果低于检索页覆盖，表明检索器找到证据页不代表 QA 层会引用目标证据。没有模型生成，也不报告回答准确率。

复现黄金校验、索引和 k=10 检索：

```powershell
.\.venv\Scripts\python.exe -m papertrail.gold --sources evals/pt8-development-sources.yaml --gold evals/pt8-development-gold-20261023.jsonl --minimum-questions 1
.\.venv\Scripts\python.exe -m papertrail index --sources evals/pt8-development-sources.yaml --selection .local/pt8-development-selection.jsonl --db .local/pt8-development.sqlite3
.\.venv\Scripts\python.exe -m papertrail vector-build --db .local/pt8-development.sqlite3 --artifact .local/pt8-development.vectors.joblib
.\.venv\Scripts\python.exe -m papertrail.evaluate --compare --db .local/pt8-development.sqlite3 --gold evals/pt8-development-gold-20261023.jsonl --k 10 --minimum-questions 1 --modes bm25 vector hybrid --vector-artifact .local/pt8-development.vectors.joblib --trace-out .local/pt8-development-retrieval-k10.json
```

公开组累计 12 篇论文、22 道题，仍低于 PT1 的 30–60 篇和至少 40 题目标。PT6 是首轮已暴露 holdout；未来需另冻结足够规模的新测试论文组，不能将 PT6 或开发组结果重新描述为盲测。
