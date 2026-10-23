# PT5：公开许可论文组与页级黄金题

日期：2026-10-23

## 冻结范围

冻结组 `pt5-public-real-20261023` 含 3 篇公开论文、6 道人工编写题，每篇 2 题。三篇均由 PLOS 官方出版者端点下载，官方文章页标明 CC BY 4.0。PDF 来源版本、官方记录、许可证据、下载地址、本地路径及 SHA-256 均登记在 `configs/public-paper-license-registry.json` 与 `evals/pt5-public-source-manifest-20261023.json`。

| 论文 | 来源版本 | PDF 页数 | SHA-256 |
|---|---|---:|---|
| Workflow for detecting biomedical articles with underlying open and restricted-access datasets | 版本记录；2024-05-08 | 20 | `2aa23da30ca26e61ecff0389045f2f04110f093343b60312144211037b20baa4` |
| Ten simple rules to make computable knowledge shareable and reusable | 版本记录；2024-06-20 | 9 | `e887af39e1982b7e164100bf591409340fdbed78153fc11f8a04696518123122` |
| Ten quick tips for ensuring machine learning model validity | 版本记录；2024-09-19 | 12 | `176e2321b47a2cf1c726372eafeb24f47b73e9b3d75c91c98545af4dcc5835b5` |

公开出版者记录：[Workflow](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0302787)、[Computable knowledge](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1012179)、[Machine-learning validity](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1012402)。每篇页面列出 DOI 与 CC BY 4.0 许可。语料仅从上述官方出版者页面下载，不含私人 PDF。

## 黄金题与复现

题目位于 `evals/pt5-public-gold-20261023.jsonl`，来源配置位于 `evals/pt5-public-sources.yaml`。每题证据指针绑定来源 ID、文件名、SHA-256、PDF 物理页码和短引文。每篇所用原文摘录总长少于 25 个英文词；题目按论文分组，不跨组复用证据。

```powershell
.\.venv\Scripts\python.exe scripts/validate_public_license_registry.py
.\.venv\Scripts\python.exe -m papertrail.gold --sources evals/pt5-public-sources.yaml --gold evals/pt5-public-gold-20261023.jsonl --minimum-questions 1
```

冻结清单同时记录黄金文件 SHA-256、问题数和来源 PDF 哈希。验证器逐页抽取 PDF 并比对引文；它不调用模型。`fetch_pt5_public_group.py` 仅允许 CC BY 4.0 与 PLOS 官方域，校验 PDF MIME、文件头、重定向域和哈希，并拒绝写出项目目录。

## 排除项与范围

另外两篇候选的许可虽已核验为 CC BY 4.0，但官方 PDF 端点分别返回浏览器 PoW 页面/403 和空 HTTP 202，故未纳入冻结组；没有尝试绕过验证，也没有使用第三方镜像。PT1 的 Nature 论文仍是另一组 8 题开发集，不计入本组。

PT5 目前只有 3 篇论文、6 道题，是可复现的公开论文小型诊断组；不能据此宣称独立测试集、广泛论文覆盖或泛化能力。PT1–PT3 的评测与账本未改动，本阶段没有模型调用，API 预算仍为 `$0.0974504 / $0.50`。

## 离线检索诊断

冻结组只用于诊断，不作为盲测。三篇 PDF 共 41 页、467 个索引块；使用 `papertrail-s1-4`，索引 revision 为 1。结果摘要在 `evals/pt5-public-retrieval-summary-20261023.json`；完整轨迹留在忽略目录 `.local/`，不包含私有来源。

| 模式 | Recall@5 | MRR@5 | 完整短证据覆盖@5 | Recall@10 | MRR@10 | 完整短证据覆盖@10 |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 1.000 | 0.917 | 6/6 | 1.000 | 0.917 | 6/6 |
| 字符 TF-IDF + SVD 向量 | 1.000 | 0.917 | 6/6 | 1.000 | 0.917 | 6/6 |
| BM25 + 向量 RRF | 1.000 | 0.917 | 6/6 | 1.000 | 0.917 | 6/6 |
| BGE dense | 未运行 | 未运行 | 未运行 | 未运行 | 未运行 | 未运行 |

Recall 为目标 PDF 页的微平均召回；MRR 按去重后的物理页排名计算；完整短证据覆盖要求该题每条 gold quote 均出现在命中的目标页检索文本中。当前每题仅一条证据，因此三种已运行模式都达到 6/6；不能据此推断多证据或更大语料表现。BGE 模型缓存存在，但锁定环境缺少 `sentence_transformers` 和 `torch`，故未运行神经 dense；`vector` 是字符 TF-IDF + SVD，不冒称 dense embedding。无 API 调用。

三篇论文分别均为 2/2 页命中、2/2 完整证据覆盖；未命中目标论文、错页或证据不全均为 0。再用 `ask(..., generate=False)` 对 6 题逐题走本机问答引用路径，全部返回 `verified_excerpts`，引用均含 gold 页和对应短引文，`model_name` 均为空。为满足该路径，修订了几题措辞以匹配原文术语；这是已接触的开发诊断集，检索分数存在调参偏差。该题组只测来源内事实定位，尚无跨文献、复杂多跳或不可回答题。

可复现命令：

```powershell
.\.venv\Scripts\python.exe -m papertrail.evaluate --compare --db .local/pt5-public-eval.sqlite3 --gold evals/pt5-public-gold-20261023.jsonl --k 5 --minimum-questions 1 --modes bm25 vector hybrid --vector-artifact .local/pt5-public-eval.vectors.joblib --trace-out .local/pt5-public-retrieval-k5.json
.\.venv\Scripts\python.exe -m papertrail.evaluate --compare --db .local/pt5-public-eval.sqlite3 --gold evals/pt5-public-gold-20261023.jsonl --k 10 --minimum-questions 1 --modes bm25 vector hybrid --vector-artifact .local/pt5-public-eval.vectors.joblib --trace-out .local/pt5-public-retrieval-k10.json
```
