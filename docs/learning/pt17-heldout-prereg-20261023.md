# PT17 新论文独立留出集预登记

## 来源与许可

来源为 3 篇此前未进入评测库的 PLOS Computational Biology 论文。PLOS 官方 PDF 与文章页均确认 CC BY 许可；本地 SHA-256、DOI、下载链接和许可证据见 `evals/pt17-heldout-source-manifest-20261023.json`。对照已有 fixtures，DOI 与 PDF 哈希重叠数均为 0。论文原 PDF 保持只读。

- *Ten simple rules for navigating AI in science*，DOI `10.1371/journal.pcbi.1013259`；[PLOS 文章与许可](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1013259)。
- *Ten simple rules for effective research data management*，DOI `10.1371/journal.pcbi.1013779`；[PLOS 文章与许可](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1013779)。
- *Ten simple rules for training by researchers for researchers in a rapidly evolving workforce*，DOI `10.1371/journal.pcbi.1013408`；[PLOS 文章与许可](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1013408)。

## 冻结题集

5 道题：事实定位 1、跨论文 1、多跳 2、不可回答 1。答案与最小证据集在 `evals/pt17-heldout-gold-20261023.jsonl`；7 条证据已按 PDF SHA-256、物理页码和原文逐字校验。金标在模型调用前冻结，运行器只读取问题，绝不把答案或证据指针发给模型。

索引固定为 3 篇论文、111 个章节、469 个片段。题集、来源清单、索引、QA/检索代码、提示词和单次运行器哈希见 `evals/pt17-model-e2e-prereg-20261023.json`。问题、索引和评分均为单次运行；不按结果调参或重跑。

## 运行与费用

模型固定 DeepSeek `deepseek-flash`，BM25，证据上限 5，温度 0，输出上限 800 tokens。只发送问题和通过来源验证的检索短摘录；不发送私人材料或完整 PDF。

起始主账 `$0.43651278`，余额 `$0.06348722`。阶段硬限 `$0.05`，所以总账至少保留 `$0.01348722`。每次请求按实际长度预留，最多 30 次、每次最多 2,400 字符；预算超限则请求不发送。执行一次：

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe scripts\evaluate_pt17_model_e2e_once.py --run-once
```

机器评分只核对金标页、短语、引文及来源有效性；不等于语义准确率。需独立人工复核。3 篇论文和 5 道题仅作小样本诊断。

## 官方许可与下载来源

下载自 PLOS 官方 PDF 端点；CC BY 4.0 [许可文本](https://creativecommons.org/licenses/by/4.0/)。官方文章页标示发布时间及 Creative Commons Attribution License。
