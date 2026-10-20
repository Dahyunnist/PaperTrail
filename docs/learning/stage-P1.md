# P1 学习记录：本机语义检索

## 实现

新增 `bge` 与 `hybrid_bge` 检索模式，使用本机缓存的 `BAAI/bge-small-zh-v1.5`。向量索引按 chunk ID 摘要和数据库 revision 校验，索引与原文保持分离；重新索引后自动重建。模型默认离线加载 CPU，也可通过 `PAPERTRAIL_BGE_MODEL` 指定本机目录。原 BM25、旧 LSA 和默认模式保持原样。

本机 cross-encoder 缓存缺少完整模型权重，因此未伪装成可用 reranker，也未更改默认检索。后续取得完整本地权重后再加入同一黄金集对照。

## 对照

使用 12 篇论文 pilot、31 道可回答题、top-5 去重页面。每题只使用原 PDF 作为证据来源。数据来自 2026-10-20 本机运行；查询耗时受机器负载影响。

| 模式 | 页 Recall@5 | MRR@5 | nDCG@5 | 平均查询耗时 |
|---|---:|---:|---:|---:|
| BM25 | 0.355 | 0.261 | 0.266 | 10.6 ms |
| 旧 LSA | 0.290 | 0.141 | 0.168 | 51.2 ms |
| 旧混合 | 0.484 | 0.242 | 0.297 | 29.6 ms |
| BGE | 0.452 | 0.241 | 0.276 | 213.7 ms |
| BM25+BGE RRF | 0.484 | 0.266 | 0.312 | 33.5 ms |

BGE 单独检索召回 14/31 页，旧混合为 15/31。BGE 混合保持旧混合的 15/31，排序指标略高。提升仅来自 31 题 pilot，不能据此宣称稳定优势；默认仍为 BM25。BGE 对跨论文题为 2/2，样本太少，不能外推。

## 运行与验证

从仓库根目录执行：

```powershell
$env:HF_HUB_OFFLINE = "1"
python -m papertrail.evaluate --compare --db .local/papertrail-s1-final.sqlite3 --gold evals/gold.jsonl --k 5 --trace-out .local/p1-bge-eval.json
python -m pytest -q
```

语义运行依赖在可选 `requirements-rag.txt` 中。本机评测使用已有隔离环境和 Hugging Face 缓存，未下载模型或调用云服务。12 项测试通过。

## 经验

语义向量带来跨语言候选召回，但候选排序仍影响页定位。评测应同时记录页 Recall、MRR、nDCG 和耗时，并先验证增益是否足以覆盖推理成本。缓存模型和向量索引可避免逐题重复加载。
