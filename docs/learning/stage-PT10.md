# PT10：补充计算实践与数值数据开发集

日期：2026-10-23

## 许可与冻结

PT10 新增三篇 PLOS Computational Biology 论文。官方页面明确标示 Creative Commons Attribution License；出版日期、出版者下载地址、许可证据页、本地 SHA-256 与黄金集哈希见 registry 和 manifest。

| 论文 | DOI | PDF 页数 | SHA-256 |
|---|---|---:|---|
| [Good enough practices in scientific computing](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005510) | 10.1371/journal.pcbi.1005510 | 20 | `ed60d4b71c36d650757c7adfe1d52afb5b6b125b7b747f74f79d5ad80e94c017` |
| [Ten quick tips for getting the most scientific value out of numerical data](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1006141) | 10.1371/journal.pcbi.1006141 | 21 | `030137d7ea8d31c1004976b005d9817f4cefcf686f8ae8acc8472964ec98a816` |
| [Ten simple rules for leveraging virtual interaction to build higher-level learning into bioinformatics short courses](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1010220) | 10.1371/journal.pcbi.1010220 | 17 | `ad4f59ea9b8fa6941db4184ea8b648c099ce55c3db57943206b613a90962d30a` |

黄金集四题，包含三道事实定位和一道跨论文比较题；五条短证据均通过 PDF 页文本、来源 SHA-256 和物理页码核验。黄金集 SHA-256 为 `a5fa387dc80a977241c7e05fc697d7154134c608058368389a0f565c7b3d5a3f`。PT10 是开发诊断组，与 PT6、PT9 测试论文不重叠。

## 离线诊断

索引涵盖 58 个 PDF 页和 795 个文本块，解析器 `papertrail-s1-4`。未运行 Dense BGE：环境缺少 `sentence_transformers` 与 `torch`。未调用模型或 API。

| 模式 | Recall@5 | MRR@5 | 完整目标页@5 | 完整引文@5 | Recall@10 | MRR@10 | 完整目标页@10 | 完整引文@10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BM25 | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 |
| 字符 TF-IDF + SVD | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 |
| BM25 + 向量 RRF | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 |

三种模式结果相同。按论文看，“Good enough practices in scientific computing” 两题均有目标文档命中但没有命中目标页；“numerical data” 两题中一题完整命中；虚拟课程题完整命中。跨论文题的两页均未命中。样本仅四题，不能据此给出泛化结论。

实际 QA 证据路径对四题均返回 `verified_excerpts`，模型名为空。最终摘录覆盖 2/5 条黄金页、2/5 条精确短引文。检索指标没有体现 QA 层对目标证据的引用质量。

## 复现

```powershell
.\.venv\Scripts\python.exe -m papertrail.gold --sources evals/pt10-development-sources.yaml --gold evals/pt10-development-gold-20261023.jsonl --minimum-questions 1
.\.venv\Scripts\python.exe -m papertrail index --sources evals/pt10-development-sources.yaml --selection .local/pt10-development-selection.jsonl --db .local/pt10-development.sqlite3
.\.venv\Scripts\python.exe -m papertrail vector-build --db .local/pt10-development.sqlite3 --artifact .local/pt10-development.vectors.joblib
.\.venv\Scripts\python.exe -m papertrail.evaluate --compare --db .local/pt10-development.sqlite3 --gold evals/pt10-development-gold-20261023.jsonl --k 10 --minimum-questions 1 --modes bm25 vector hybrid --vector-artifact .local/pt10-development.vectors.joblib --trace-out .local/pt10-development-retrieval-k10.json
```

公开许可语料累计 18 篇论文、32 道题。PT1 原定规模仍未达到；PT9 未暴露测试集保持冻结，没有在本阶段触碰。
