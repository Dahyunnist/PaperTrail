# PT7：新增三篇许可明确的开发论文

日期：2026-10-23

## 语料与冻结

本阶段新增三篇 PLOS Computational Biology 论文。PLOS 出版页面均明确标示 Creative Commons Attribution License；记录、版本日期、官方 PDF 地址、CC BY 4.0 法律文本链接及本地 PDF SHA-256 写入 `configs/public-paper-license-registry.json` 和 `evals/pt7-public-source-manifest-20261023.json`。

| 论文 | DOI | PDF 页数 | SHA-256 |
|---|---|---:|---|
| [Ten simple rules for innovative dissemination of research](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1007704) | 10.1371/journal.pcbi.1007704 | 12 | `f608cdf588ac44ef34797a4dac35fa2b4da1800ab038b4ccc3453742d709a452` |
| [Ten simple rules for reporting information on species interactions](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1010362) | 10.1371/journal.pcbi.1010362 | 10 | `629c33befe0160b0cb463799af659a35fdf49203720f55bd0371bef4d55fe073` |
| [Ten simple rules for designing analogue science games](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1009009) | 10.1371/journal.pcbi.1009009 | 16 | `0be11b02dd8e7631d0c1ee7ca41c9ab36c44d8e98289080bb1a9fa45aa4a3344` |

三篇论文与 PT5、PT6 的论文均不重叠。六道开发题含三道事实定位、一题跨论文比较、一题跨页多跳和一道不可回答题。黄金集 SHA-256 为 `1988b33fafe7817277fa54ab1bbf240b159dd7d856f0ee1efa76f2216ee2463d`。问题使用英文，匹配源文语言；最终题目仅作开发诊断，允许用于理解失败，不作为独立测试。

## 离线检索诊断

使用 PT7 三篇论文建立独立 SQLite 索引：69 个解析章节、444 个索引块，解析器为 `papertrail-s1-4`。字符 TF-IDF + SVD 是本地稀疏特征的降维实验，不代表神经密集检索。未安装 `sentence_transformers` 与 `torch`，未运行 BGE，也没有模型或 API 调用。

指标中，Recall@k 是至少命中一页目标物理页的问题比例；MRR 对目标物理页排序；全部页覆盖要求多页题的每个目标页都出现；完整引文覆盖要求所有黄金短引文均出现在对应目标页检索文本中。

| 模式 | Recall@5 | MRR@5 | 全部目标页@5 | 完整引文@5 | Recall@10 | MRR@10 | 全部目标页@10 | 完整引文@10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BM25 | 0.600 | 0.400 | 0.400 | 0.400 | 0.800 | 0.422 | 0.600 | 0.600 |
| 字符 TF-IDF + SVD | 1.000 | 0.667 | 0.800 | 0.400 | 1.000 | 0.667 | 1.000 | 0.800 |
| BM25 + 向量 RRF | 0.600 | 0.500 | 0.400 | 0.400 | 0.800 | 0.533 | 0.600 | 0.600 |

PT7 只用于开发诊断，题目和语言形式可根据开发行为调整。结果显示向量模式在 k=10 命中全部五道可回答题的目标页，但完整引文覆盖为 0.800；RRF 仅为 0.600。BM25 与 RRF 均未命中两道传播研究论文目标页，原因是目标物理页排序靠后。不可回答题在三种模式下均返回检索候选；检索非空不能判定系统能否正确拒答。

进一步运行实际证据摘录路径 `ask(..., generate=False)`，五道可回答题共 7 条黄金证据。最终显示摘录只覆盖 3/7 个黄金页、1/7 条精确黄金短引文，且全部状态为 `verified_excerpts`、模型名为空。检索目标页命中不等于 QA 最终引用页命中。这个缺口与 PT6 的失败一致，因此不报告自然语言回答正确率。

## 复现与限制

```powershell
.\.venv\Scripts\python.exe -m papertrail.gold --sources evals/pt7-development-sources.yaml --gold evals/pt7-development-gold-20261023.jsonl --minimum-questions 1
.\.venv\Scripts\python.exe -m papertrail index --sources evals/pt7-development-sources.yaml --selection .local/pt7-development-selection.jsonl --db .local/pt7-development.sqlite3
.\.venv\Scripts\python.exe -m papertrail vector-build --db .local/pt7-development.sqlite3 --artifact .local/pt7-development.vectors.joblib
.\.venv\Scripts\python.exe -m papertrail.evaluate --compare --db .local/pt7-development.sqlite3 --gold evals/pt7-development-gold-20261023.jsonl --k 10 --minimum-questions 1 --modes bm25 vector hybrid --vector-artifact .local/pt7-development.vectors.joblib --trace-out .local/pt7-development-retrieval-k10.json
```

本阶段后公开组累计 9 篇论文、18 道题，PT5 与 PT7 是开发组；PT6 首轮 holdout 已经暴露，不能再当作独立测试。PT1 的原目标仍为 30–60 篇、至少 40 题。后续还需增加有明确许可的论文、题目与一个未暴露的论文隔离测试组，才能接近预定规模。完整 k=5、k=10 原始轨迹仅存于忽略目录 `.local/`，没有提交 PDF 原文或全文索引。
