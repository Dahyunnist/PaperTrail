# PT-1 QASPER 外部数据源审计（2026-11-13）

## 核查结论

本轮只核对官方 ACL Anthology 论文页与 Hugging Face `allenai/qasper` 数据卡，没有下载数据、PDF 或读取本机私人论文。

- ACL Anthology 论文摘要说明 QASPER 有 5,049 个问题、覆盖 1,585 篇 NLP 论文；问题由读标题/摘要的 NLP 从业者撰写，另一组从业者回答并提供支持证据。论文页链接：<https://aclanthology.org/2021.naacl-main.365/>。
- 数据卡将数据集许可标为 CC BY 4.0，并说明 `evidence` 可指向段落、图或表，`highlighted_evidence` 是标注者选出的句子；来源全文来自 S2ORC。数据卡：<https://huggingface.co/datasets/allenai/qasper>。
- 数据集许可不能自动证明其中每篇论文 PDF 可复制或再分发。数据卡没有给出逐论文许可登记，因此本阶段不下载/提交任何 QASPER 论文 PDF，也不把其文本纳入 PT 索引。
- QASPER evidence 是抽取全文的段落或图表引用，不提供 PaperTrail 所需 PDF 物理页码与原始 PDF 字符 span。段落到 PDF 页码/span 映射尚未建立和逐篇验证，不能直接转换为 PaperTrail gold。
- QASPER 标注由两组从业者分别提出问题、回答并标 evidence；它不是本项目对冻结题目的独立双人复核和裁决，不能替代 PT-1 人工 gold。

## 决定与后续

当前不导入 QASPER gold，不重映射 PDF，不报告它作为 PT-1 真实指标。PT-1 40 题仍等待用户安排的两名标注者与复核者。

PT-2 继续使用已登记、逐篇核验 CC BY 4.0 的公开 fixture 和合成回归。公开 fixture 结果可复现，但 5 题冻结组只作诊断，不调参、不外推到真实盲测。PT-3 继续以 fake generator 合成回归验证引用与覆盖契约，不声称真实回答质量。

本审计不调用模型，不读取用户私人 PDF，不下载外部 PDF，不改变冻结 gold。
