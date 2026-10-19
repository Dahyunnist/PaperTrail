# S4 学习记录：跨论文证据并列与立场标注

## 阶段目标

对一个主题和待比较论断，从多篇原始论文收集可核查原句，按逻辑论文分组，并允许用户逐条标记支持、反对、适用条件、背景或不清楚。用户可以记录自己的研究空白候选及其证据依据。每条证据继续携带 S3 的版本 SHA、PDF 页、chunk 和解析器版本。

## 为什么立场由用户标注

当前没有本地语言模型。检索到一句“uses categorical noise”只说明它提到了该术语，并不自动证明它支持给定论断；论文之间还可能比较不同基准、数据集或适用条件。系统因此只收集候选摘录并展示原论文元数据，初始标签恒为 `unclassified`。用户选择标签时可以填写理由，来源文字从未被重写为机器综合结论。

研究空白也不从“没有检索到反例”自动推导。用户可以把比较后产生的观察保存为 `user_proposed` gap candidate，并关联本次比较中的 evidence ID；报告始终把候选意见与论文原文分开。

## 运行方式

```powershell
python -m papertrail compare --db .local/papertrail.sqlite3 --topic "TabDDPM categorical diffusion" --claim "uses multinomial diffusion for categorical features" --limit-papers 5
python -m papertrail compare-label --db .local/papertrail.sqlite3 --evidence-id <ID> --label conditions --rationale "Only the categorical columns use this process."
python -m papertrail compare-gap --db .local/papertrail.sqlite3 --comparison-id <ID> --note "No direct robustness comparison is present in this pilot." --evidence-id <EVIDENCE_ID>
python -m papertrail compare-report --db .local/papertrail.sqlite3 --comparison-id <ID>
```

对照查询将主题中的关键词分别检索后合并候选，避免在一个 AND 查询里因主张措辞更具体而漏掉相关论文；摘录至少共享一个主题/论断关键词，所以它只表示候选相关，不表示支持。候选优先覆盖不同论文，再允许每篇显示第二条。原文来源必须是未被改动的 PDF，页码短句需要重新核验，阅读笔记和 OCR 派生块都排除。

## 实测与验证

真实 pilot 的 TabDDPM 比较在五篇不同论文间收集到核验摘录，初始立场均未分类。例子中包含原始 TabDDPM 的离散特征扩散描述，也包含其他论文关于分类列、噪声和相关基线的说明；用户需要判断它们是支持、条件还是背景，不能把共同术语误判为冲突。合成双论文测试覆盖不同描述、默认不分类、人工标注支持/反对、理由保存及空白候选依据关联。S4 测试加入后，全量测试为 9 项通过。

## 数据边界和限制

- 比较记录、证据标签、标注理由和 gap candidates 保存在本地索引库独立表，不修改论文 chunks 或原文件。
- 立场标签是用户的工作判断，不是原作者明确声明；最终 Web 界面应始终显示标注人、理由和来源页，避免误解。
- 当前小型语料的关键词扩展仍会找到“只是提及术语”的片段，需要人工审阅。研究空白是待核验的问题清单，不是已经证明的研究空白。
- 还没有向量驱动的扩展对照、自动 claim 归类或模型综合；这些能力不能绕过引用校验和人工标注边界。

最终用户体验和 S0–S5 阶段范围见[产品契约](../product-contract.md)。
