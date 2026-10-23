# PT6：按论文隔离的真实公开 holdout

日期：2026-10-23

## 语料与冻结角色

PT5 的 3 篇论文、6 道题标为开发诊断组。PT6 新增 3 篇未进入 PT5 评测的官方 PLOS PDF，冻结 6 道测试题；两组来源论文完全不重叠。PT6 含 2 道跨文献题、1 道跨页多跳题、2 道事实定位题、1 道不可回答题。题、页码、短引文、PDF SHA-256 与黄金集 SHA-256 写入本目录清单。

| 论文 | DOI | PDF 页数 | SHA-256 |
|---|---|---:|---|
| [Ten simple rules for making research software more robust](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005412) | 10.1371/journal.pcbi.1005412 | 10 | `002081be65fbd42c0356d3e49ac7f49fa6202f566f50341481ead22d3cce78b2` |
| [Ten (not so) simple rules for clinical trial data-sharing](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1010879) | 10.1371/journal.pcbi.1010879 | 10 | `950c43a35649934f2375e745c792a599225e0838e9fc1527c3df5829c9b3877f` |
| [Ten simple rules for documenting scientific software](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1006561) | 10.1371/journal.pcbi.1006561 | 6 | `c2b50ad022577a957672622dec9ae0ad7ab746ef38a04ab051f007814fb76e7d` |

三篇 PLOS 文章页和 PLOS 许可政策明确适用 CC BY 4.0；条目、许可页、官方 PDF 下载地址和本地哈希见 `configs/public-paper-license-registry.json` 与 `evals/pt6-heldout-source-manifest-20261023.json`。许可页面：[PLOS 许可政策](https://journals.plos.org/plosone/s/licenses-and-copyright)、[CC BY 4.0 法律文本](https://creativecommons.org/licenses/by/4.0/)。只下载官方出版者 PDF，不含私人资料。

冻结文件：

- `evals/pt6-heldout-gold-20261023.jsonl`
- `evals/pt6-heldout-sources.yaml`
- `evals/pt6-heldout-source-manifest-20261023.json`
- `evals/pt6-heldout-retrieval-summary-20261023.json`

## 首次离线测试

评测使用完整 6 篇公开语料：67 个 PDF 页、822 个索引块、解析器 `papertrail-s1-4`。仅用 3 篇测试论文作题目目标，另外 3 篇开发论文保留为检索干扰项。Dense BGE 未运行：当前锁定环境没有 `sentence_transformers` 与 `torch`。`vector` 仅指字符 TF-IDF + SVD。未下载新运行依赖，没有模型或 API 调用。

Recall 按 gold 物理页微平均；MRR 按去重物理页排名；完整证据覆盖要求所有 gold 引文都出现在检索到的目标页文本中。

| 模式 | Recall@5 | MRR@5 | 全部目标页@5 | 完整引文@5 | Recall@10 | MRR@10 | 全部目标页@10 | 完整引文@10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BM25 | 0.750 | 0.667 | 0.600 | 0.000 | 1.000 | 0.667 | 1.000 | 0.400 |
| 字符 TF-IDF + SVD | 0.750 | 0.717 | 0.600 | 0.200 | 0.875 | 0.717 | 0.800 | 0.600 |
| BM25 + 向量 RRF | 0.875 | 0.717 | 0.800 | 0.000 | 1.000 | 0.717 | 1.000 | 0.400 |

在 Recall@10 上三篇测试论文的 gold 页都出现；引文仍常不完整。以 RRF@10 为例，Documentation 为 2/2 题完整覆盖，Robustness 为 1/3，Clinical data-sharing 为 1/2。首次 holdout 失败来自跨文献题两侧证据未同时召回，以及目标页命中但短引文所在块缺失。题目 ID 和逐题分类在 `.local/pt6-heldout-retrieval-k5.json` 与 `k10.json`，未把整段问题或私有路径写入汇总。

随后用 `ask(..., generate=False)` 验证实际引用路径。5 道可回答题共 9 条 gold 证据中，只有 4 条目标物理页进入显示引用，精确短引文命中为 0/9；QA 返回的是未经综合的 `verified_excerpts`，`model_name` 为空。不可回答题的正确拒答无法靠本次禁用生成的检索运行判定。

PT6 题目冻结后完成了这一轮唯一 holdout 评测。此结果不用于调整检索器或题目；如依据这些失败修正系统，PT6 之后只能叫已暴露回归集。不能据 6 题推断泛化。PT1 原定 30–60 篇、至少 40 题的规模目标仍未达到；当前公开集为 6 篇、12 题。

## 索引和版本路径

PT4 的 `tests/test_s1.py::test_reconcile_updates_changed_paths_and_removes_deleted_sources` 检查旧 SHA 解绑、替换版本入库和索引 revision 递增；同文件也验证向量索引在 revision 变化后刷新。PT4 完整测试在当前锁定环境再次全过。PT5 开发集另逐题走过本机证据校验路径，6/6 引文都与实际 PDF 页和 SHA 相符；PT6 首测暴露了检索候选到最终引用短摘录之间的覆盖缺口。详见 [PT4](stage-PT4.md) 和 [PT5](stage-PT5.md)。

复现检索评测：

```powershell
.\.venv\Scripts\python.exe -m papertrail.evaluate --compare --db .local/pt-public-full.sqlite3 --gold evals/pt6-heldout-gold-20261023.jsonl --k 5 --minimum-questions 1 --modes bm25 vector hybrid --vector-artifact .local/pt-public-full.vectors.joblib --trace-out .local/pt6-heldout-retrieval-k5.json
.\.venv\Scripts\python.exe -m papertrail.evaluate --compare --db .local/pt-public-full.sqlite3 --gold evals/pt6-heldout-gold-20261023.jsonl --k 10 --minimum-questions 1 --modes bm25 vector hybrid --vector-artifact .local/pt-public-full.vectors.joblib --trace-out .local/pt6-heldout-retrieval-k10.json
```
