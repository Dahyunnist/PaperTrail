# PT-3 部分覆盖与引用绑定离线回归（2026-11-14）

## 回归场景

测试使用两篇临时生成的合成 PDF。固定检索步骤只为 Alpha 子问题提供可核验证据，Beta 子问题没有召回结果；生成/审查步骤由测试替身给出确定的 Alpha 支持 claim，不连接模型服务。

系统必须返回 `status=generated_partial`、`completion_state=partial`，在 `missing_subquestions` 中列出 Beta 问题，并在回答中标出未覆盖原因。唯一保留的 claim 必须只映射到 Alpha 的支持证据；其 SHA-256、PDF 物理页码和原文 quote 与 claim 主引用一致，且 quote 能用真实 PDF 字节、指定页码和原文重新校验。不得把缺失的 Beta 槽补成无来源 claim 或 citation。

## 指标口径与验证

本回归是契约测试，不是问答准确率样本。场景中有 2 个子问题槽位，支持证据覆盖为 **1/2**，因此 completion 必须为 `partial`；claim/citation 完整性按 SHA + PDF 物理页 + 原文 quote 三项逐条核验，不以检索分数或模型自评替代。定向 pytest 覆盖部分回答、缺失槽位、跨槽映射拒绝和引用失败路径，共 **4 项通过**。

数据仅来自仓库测试中临时构造的合成 PDF；固定步骤的结果由测试替身提供。没有读取私人 PDF、修改 gold 或调用模型。这证明代码对已知部分覆盖场景的处理，不证明真实论文 claim 正确率、真实语料完整覆盖或人工 gold 已验收。PT-1 真实 gold 仍为 **0/40**，真实论文质量验证需等两名标注者独立完成 A/B CSV、仲裁和来源核验后再进行。
