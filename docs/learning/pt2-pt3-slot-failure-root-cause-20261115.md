# PT-2/PT-3 引文槽失败根因复核（2026-11-15）

## 范围与冻结基线

- 只用已登记的 PT7/PT8/PT10/PT11 CC BY 4.0 development 集，fresh 临时索引，model calls 为 0。
- 原始逐题报告冻结不改：`evals/pt2-pt3-public-development-diagnostic-20261115.json`，SHA-256 `FCFA9D1E2C6598ABD9FBC46E307D2A5B31A523B26FADA90C5392C37DD74C22AD`。
- 候选对照仅把无模型 `ask` 的检索模式从 `bm25` 换为 `bm25_expanded`；不读题目、gold 或引文原文输出。临时报告保存在 `.tmp/`，不提交。

## 逐题对照

全部 16 道可回答题的 cited gold page slots 与 gold phrase slots 前后完全相同；source validation failures 均为 0。变化只发生在摘录总数：PT7 第 5 题 `4→3`，PT8 第 3 题 `3→2`；没有新增引用槽或 gold phrase 覆盖。

| 开发组/题序 | 类型 | gold 页槽引用：BM25→扩展 | 短语槽：BM25→扩展 |
|---|---|---:|---:|
| PT7 / 1 | fact_location | 0/1→0/1 | 0/1→0/1 |
| PT7 / 2 | fact_location | 1/1→1/1 | 0/1→0/1 |
| PT7 / 3 | fact_location | 1/1→1/1 | 1/1→1/1 |
| PT7 / 4 | cross_paper | 1/2→1/2 | 0/2→0/2 |
| PT7 / 5 | multi_hop | 0/2→0/2 | 0/2→0/2 |
| PT8 / 1 | fact_location | 0/1→0/1 | 0/1→0/1 |
| PT8 / 2 | fact_location | 1/1→1/1 | 0/1→0/1 |
| PT8 / 3 | fact_location | 0/1→0/1 | 0/1→0/1 |
| PT10 / 1 | fact_location | 0/1→0/1 | 0/1→0/1 |
| PT10 / 2 | fact_location | 1/1→1/1 | 1/1→1/1 |
| PT10 / 3 | fact_location | 1/1→1/1 | 1/1→1/1 |
| PT10 / 4 | cross_paper | 0/2→0/2 | 0/2→0/2 |
| PT11 / 1 | fact_location | 1/1→1/1 | 1/1→1/1 |
| PT11 / 2 | fact_location | 1/1→1/1 | 1/1→1/1 |
| PT11 / 3 | fact_location | 1/1→1/1 | 0/1→0/1 |
| PT11 / 4 | cross_paper | 1/2→1/2 | 0/2→0/2 |

## 根因判断与处置

报告里的深度召回使用 `bm25_expanded`，而原始无模型 `ask` 使用 `bm25`。增加 `--qa-mode` 后做了同索引模式对照，覆盖不变，故候选池模式差异不能解释主要失败，也不是修复方向。

代码层面的根因是无模型 `_ask` 不调用子问题规划；它把整题词项用于句子重合评分，再按 `score_overlap + 2 * title_overlap` 排序并截取前 `limit` 条。该规则只按词面线索挑句，不识别跨论文/多跳语义槽，也不能保证检索到的 gold phrase chunk 会成为最终引用。现有来源校验均通过，说明问题在引用覆盖选择，不是 SHA、页码或来源伪造。

没有保留算法改动：扩展 BM25 无增益且两题摘录数下降。`papertrail/qa.py` 保持基线；报告脚本仅增加受限离线模式开关和结果标签。跨论文 extractive phrase coverage 仍为 `0/6`，开发集已见且非盲测；不声称验收通过。PT-1 继续暂停，不碰私有 PDF、holdout 或模型。
