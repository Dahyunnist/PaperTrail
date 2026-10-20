# P8 学习记录：提高真实答题覆盖

## 题集边界

P6 的 34 题已被用于调试、失败分析和代码选择，现明确标为开发集。它不是独立测试集，也不能支撑泛化或简历质量声明。P8 在该开发集上做回归；下一阶段需另建冻结题集，覆盖独立论文、无答案题、跨论文、冲突和多跳。

## 修复

问答链路先让模型从最多 8 条短候选片段中筛选相关证据。证据不足时，根据问题和候选返回的短查询只补检一次。然后从筛选通过的原始 PDF 页摘录句子。PDF SHA、页码、原文逐条校验继续作为引用门槛。

最终审查逐条检查 claim 是否受引用支持、是否回答问题，并检查整题要点覆盖。若覆盖不全，整题拒答；不支持或无关的 claim 不进入回答。重排、筛选、生成与审查的 token、费用和延迟按题记录在忽略目录。

## P7 检索端到端对照

使用同一 34 题开发集、同一 `hybrid_bge_rerank` 检索与 12 页候选配置，对照摘录基线和真实 `deepseek-flash` 生成。总运行账本按每个 API 请求计费；每题明细见 `.local/p8-dev-rerank-qa.json`，逐题人工分类见 `.local/p8-dev-manual-review.json`。PDF 和个人材料未发送，API 只收到问题与短论文摘录。

| 指标 | 摘录基线 | 生成与 claim 审查 |
|---|---:|---:|
| 可答题有输出 | 29/31 | 7/31 |
| 黄金页引用命中 | 4/31 | 4/31 |
| 3 道不可答题正确拒答 | 1/3 | 3/3 |
| 不可答题错答 | 2/3 | 0/3 |
| 平均延迟 | 2,051 ms | 5,478 ms |
| 本组费用上界 | $0.0083085 | $0.041274 |

人工审查生成组全部 34 题：正确 5、部分正确 2、错误 0、可答题错误拒答 24、不可答题正确拒答 3。5 道正确答案为 S0-001、002、010、012、016。S0-015 漏掉“error 降低”的量纲；S0-020 提到数据刻画与画像，但没完整说明统计保真度不足以预测下游效用，均记为部分正确。所有展示引文都来自本机原 PDF 的匹配 SHA 和页码。11 条 claim 引文中 5 条命中黄金页；跨页但可直接支持的引用不算黄金页命中。摘录基线有输出不等于回答正确，因此只报告摘录覆盖和错误输出数，不将其包装成问答正确率。

P6 旧结果单独保留：2/31 有生成，人工分类为正确 0、部分正确 1、错误 1、可答题错误拒答 29、正确拒答 3。新运行将输出从 2 道增至 7 道；仍有 24/31 可答题被拒，质量不达生产或简历门槛。跨论文 0/2、冲突 0/3、多跳 0/1；这三类仍未解决。题集中冲突题讨论实验结论，不含真实同论文多版本对。

P8 最终两组对照共 202 次计费请求，费用上界 `$0.0495825`。生成组占 168 次请求、93,656 输入 tokens、10,981 输出 tokens；逐题费用、tokens、请求数和延迟保存在本机忽略结果。P6–P8 总账 `$0.1613298/$0.19`，包含一次因运行环境和统计实现问题废弃的 P8 尝试。生成组评测均值约 5.48 秒。少数生成请求达到输出长度上限并形成拒答；固定输出预算仍是覆盖限制。

## 限制与验证

语料只有 12 篇原论文，P6 只引用其中 10 篇；所有来源 SHA 唯一。无法证明多版本切换或版本冲突安全。P6 题集已用于调试，当前数字仅是开发集反馈；独立新题集和新论文上的复验仍未完成。

针对性测试覆盖相关证据筛选、一次定向补检、claim relevance/coverage 门槛与拒答回归。全量 pytest：25 项通过。

复跑命令：

```powershell
$env:PAPERTRAIL_LLM_PROVIDER = "openai-compatible"
$env:PAPERTRAIL_LLM_MODEL = "deepseek-flash"
$env:PAPERTRAIL_OPENAI_API_KEY_ENV = "DEEPSEEK_API_KEY"
$env:PAPERTRAIL_OPENAI_BASE_URL = "https://api.deepseek.com"
$env:PAPERTRAIL_LLM_BUDGET_USD = "0.19"
$env:PAPERTRAIL_LLM_BUDGET_FILE = ".local/p6-api-usage.json"
python -m papertrail.evaluate_qa --db .local/papertrail-s1-final.sqlite3 --gold evals/p6-gold-20261020.jsonl --out .local/p8-dev-rerank-qa.json --mode hybrid_bge_rerank --vector-artifact .local/papertrail-s1-final.bge.joblib
```
