# P7 学习记录：页级候选与重排消融

## 失败样本与实现

P6 中，抽取式引用仅 7/31 命中黄金页；生成式 + claim judge 为 1/31。逐题轨迹显示多个问题召回相关论文，却引用同主题其他论文或其他页。提升答案生成无法修复候选池缺页，因此 P7 先改页面候选。

实现 `hybrid_bge_wide`：把 hybrid-BGE 候选从 25 个 chunk 扩到 100 个 chunk，再按 PDF 页去重。实现 `hybrid_bge_rerank`：从同一 100-chunk 候选中取前 12 个原文页，发送最多 12 条短标题、页码和摘录给 `deepseek-flash` 排序。reranker 只改排序，不生成答案或引用。API 返回损坏、无效顺序或错误时退回原 RRF 顺序并写出错误标记。

重排请求使用 DeepSeek non-thinking 模式。初次测试默认 thinking 模式在 320-token 上限内耗尽思考额度，返回 `finish_reason=length` 和空 content；官方 API 提供 `thinking.type=disabled`，用后大幅降低无效输出与时延。[官方 thinking 参数](https://api-docs.deepseek.com/guides/thinking_mode/)

## 消融结果

冻结同一题集 `evals/p6-gold-20261020.jsonl`，31 道可答题，top-5 去重页面。两种模式用相同的 100-chunk hybrid-BGE 候选；未重排时保留原 RRF 页顺序。

| 模式 | 页 Recall@5 | MRR@5 | nDCG@5 | 平均耗时 |
|---|---:|---:|---:|---:|
| hybrid-BGE wide，无 LLM 重排 | 0.484 (15/31) | 0.266 | 0.312 | 190 ms |
| 相同候选池，LLM 重排 | 0.581 (18/31) | 0.391 | 0.419 | 930 ms |

LLM 重排成功 30/31 次；1 次返回无效 `page_order`，已退回原顺序。前 12 页候选池覆盖黄金页 20/31 题；11 题在候选阶段已丢失，任何重排都无法召回。重排把 3 个额外黄金页推入 top-5。题型命中：事实定位 11/20、方法比较 3/5、跨论文 2/2、多跳 0/1、冲突 2/3。样本有限，不能把单次提升视为稳定泛化。

整段 P7 实验（含早期格式失败与复跑）使用 169 次 API 请求，费用上界 `$0.0524811`。P6+P7 总账本 `$0.0630111`，未超过 `$0.19`。时延约为 wide baseline 的 4.9 倍。检索仍有高拒答成本与长尾延迟，跨论文/多跳也未全面解决；因此 LLM reranker 保持可选，默认仍为 BM25。

## 验证和复现

```powershell
$env:PAPERTRAIL_LLM_PROVIDER = "openai-compatible"
$env:PAPERTRAIL_LLM_MODEL = "deepseek-flash"
$env:PAPERTRAIL_OPENAI_API_KEY_ENV = "DEEPSEEK_API_KEY"
$env:PAPERTRAIL_LLM_BUDGET_USD = "0.19"
python -m papertrail.evaluate --compare --db .local/papertrail-s1-final.sqlite3 --gold evals/p6-gold-20261020.jsonl --k 5 --modes hybrid_bge_wide hybrid_bge_rerank --trace-out .local/p7-rerank-ablation.json
python -m pytest -q
```

复跑还需设置 `$env:PAPERTRAIL_OPENAI_BASE_URL = "https://api.deepseek.com"` 与 `$env:PAPERTRAIL_LLM_BUDGET_FILE = ".local/p6-api-usage.json"`。轨迹和 API 账本留在忽略目录。全量测试包含池宽、去重、排序校验、错误回退和 usage 记录。

## 结论

同候选池重排提高页 Recall、MRR 和 nDCG，但多耗约 740 ms。候选池缺页是当前主要瓶颈。保持 BM25 默认，LLM 重排只作为显式实验模式。真实 cross-encoder 尚无完整权重，未做对照。准确的同论文多文件版本冲突集也尚未建立。P7 只测检索排序，没有在重排结果上重跑端到端生成验收，不能据此宣称答案质量提高。
