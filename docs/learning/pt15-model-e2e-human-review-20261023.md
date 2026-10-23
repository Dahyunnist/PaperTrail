# PT15 模型输出独立人工审阅

先独立判断下列题目和回答，再打开 gold 文件比较。不要把运行时同模型审查当成人工准确率。每条填写：支持 / 部分支持 / 不支持；并标注证据是否直接支持。

本表不含 gold 答案。PT15-05 在生成前被费用门禁拦截，PT15-06 未运行；二者不做语义评分。

## PT15-01

问题：How much unstructured interaction time do the authors suggest scheduling before data collection, and what benefit do they expect?

系统状态：generated_claims_reviewed

模型回答：作者建议在数据收集开始前安排15–30分钟的非结构化互动时间。 作者预期这种安排虽然会增加会话时间，但通过减少退出和重新收集需求来降低总体研究成本。

声明 1：作者建议在数据收集开始前安排15–30分钟的非结构化互动时间。

- 来源：Ten simple rules for research with humans；PDF 第 3 页；SHA-256 `2ac2337b4a485c4c3b54bde3f25498bcbe24f09194de77aec4468a0d4d7c9c42`
- 原文：> Schedule 15–30 min of unstructured interaction time before data collection begins.

声明 2：作者预期这种安排虽然会增加会话时间，但通过减少退出和重新收集需求来降低总体研究成本。

- 来源：Ten simple rules for research with humans；PDF 第 3 页；SHA-256 `2ac2337b4a485c4c3b54bde3f25498bcbe24f09194de77aec4468a0d4d7c9c42`
- 原文：> While this increases session time, this investment reduces overall study costs through decreased dropout and re-collection needs.

独立判断：支持 / 部分支持 / 不支持
理由：

## PT15-02

问题：How many participants did the authors recruit into an original experiment reported in this article?

系统状态：abstained

模型回答：没有找到通过原 PDF 哈希、页码和原文校验的证据；系统已拒答。

独立判断：支持 / 部分支持 / 不支持
理由：

## PT15-03

问题：What percentage of the supplemental data links in the study were no longer available?

系统状态：generated_claims_reviewed

模型回答：5.4% of the 2166 supplemental data links were no longer available.

声明 1：5.4% of the 2166 supplemental data links were no longer available.

- 来源：Measuring data rot: An analysis of the continued availability of shared data from a Single University；PDF 第 8 页；SHA-256 `244d7114730d1285dc6a082845c42c8e7bef8a7a96a1df371706f6b266dea87b`
- 原文：> In total, 118 (5.4%) of the 2166 supplemental links were no longer available.

- 来源：Measuring data rot: An analysis of the continued availability of shared data from a Single University；PDF 第 1 页；SHA-256 `244d7114730d1285dc6a082845c42c8e7bef8a7a96a1df371706f6b266dea87b`
- 原文：> After testing, 5.4% the 2166 sup- plemental data links were found to be no longer available.

独立判断：支持 / 部分支持 / 不支持
理由：

## PT15-04

问题：Which link type was least likely to disappear, and how did its loss rate compare with URLs?

系统状态：generated_claims_reviewed

模型回答：DOIs were the type of shared link that was least likely to disappear. The loss rate of DOIs, the least-likely-to-disappear link type, was 1.7%. URL loss was 5.9% averaged over time. The DOI loss rate (1.7%) was 4.2 percentage points lower than the URL loss rate (5.9%).

声明 1：DOIs were the type of shared link that was least likely to disappear.

- 来源：Measuring data rot: An analysis of the continued availability of shared data from a Single University；PDF 第 1 页；SHA-256 `244d7114730d1285dc6a082845c42c8e7bef8a7a96a1df371706f6b266dea87b`
- 原文：> DOIs were the type of shared link that was least likely to disappear with a 1.7% loss, with URL loss at 5.9% averaged over time.

声明 2：The loss rate of DOIs, the least-likely-to-disappear link type, was 1.7%.

- 来源：Measuring data rot: An analysis of the continued availability of shared data from a Single University；PDF 第 1 页；SHA-256 `244d7114730d1285dc6a082845c42c8e7bef8a7a96a1df371706f6b266dea87b`
- 原文：> DOIs were the type of shared link that was least likely to disappear with a 1.7% loss, with URL loss at 5.9% averaged over time.

声明 3：URL loss was 5.9% averaged over time.

- 来源：Measuring data rot: An analysis of the continued availability of shared data from a Single University；PDF 第 1 页；SHA-256 `244d7114730d1285dc6a082845c42c8e7bef8a7a96a1df371706f6b266dea87b`
- 原文：> DOIs were the type of shared link that was least likely to disappear with a 1.7% loss, with URL loss at 5.9% averaged over time.

声明 4：The DOI loss rate (1.7%) was 4.2 percentage points lower than the URL loss rate (5.9%).

- 来源：Measuring data rot: An analysis of the continued availability of shared data from a Single University；PDF 第 1 页；SHA-256 `244d7114730d1285dc6a082845c42c8e7bef8a7a96a1df371706f6b266dea87b`
- 原文：> DOIs were the type of shared link that was least likely to disappear with a 1.7% loss, with URL loss at 5.9% averaged over time.

独立判断：支持 / 部分支持 / 不支持
理由：

## PT15-05

问题：What should someone clarify before jumping into an unfamiliar codebase?

状态：预算拦截，模型未作答。

## PT15-06

问题：What do the data-sharing study and code-use guide recommend to make research resources easier for others to reuse?

状态：未运行。

## Gold 解封后的对照

完成人工判断并提交后，再比对 `evals/pt15-heldout-gold-20261023.jsonl`。人审前不汇报语义准确率。
