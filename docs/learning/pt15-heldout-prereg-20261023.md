# PT15 新论文盲测预登记

## 试验边界

PT15 使用三篇新论文、六题。DOI 与本地 PDF 哈希均未出现在 PT5–PT14 旧评测清单；PDF 哈希扫描也未发现 `evals/fixtures` 内重复。仅 PT15 独立索引，不读取 PT9/PT12 冻结语料或结果。

题目与证据页先于任何模型请求编写，并用本地 PDF 哈希、物理页码和短引文核验。gold 与题目不发送给模型。完整题集 SHA-256、三份来源 PDF、索引库、QA 提示词函数、运行器、评分器和依赖代码哈希见 `evals/pt15-model-e2e-prereg-20261023.json`。

## 锁定模型与评分

- 模型：DeepSeek API `deepseek-flash`，OpenAI-compatible，温度 0，最多 800 输出 token；峰值单价输入 `$0.30/M`、输出 `$1.32/M`。
- QA：BM25、每题最多 5 条证据、真实生成；拆题、证据筛选、生成、修复和同模型支持性/覆盖审查均纳入同一账本。
- 独立机器评分只计算哈希/页码命中、黄金短语覆盖、精确片段与可见引文的原文校验；它不判语义正确。运行时同模型审查不算独立准确率审查。
- 模型结果必须再交独立人工审阅；完成人审之前不报告语义正确率。
- 总账起点已用 `$0.42856722`，余 `$0.07143278`。本次峰值预留硬限 `$0.065`，至少留 `$0.00643278`；累计支出硬限 `$0.50`。每次请求发送前均执行峰值门禁。
- 评测脚本只允许第一次运行；禁止根据 PT15 结果调参或重跑。

## 来源与许可

三篇论文均为 PLOS 官方页面所列 CC BY 4.0 开放获取。再用需注明作者与来源。

- Coates MK, Sava TV, Tashjian SM. 2025. [Ten simple rules for research with humans](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1013362)。
- Briney KA. 2024. [Measuring data rot](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0304781)。
- Pilgrim C, Kent P, Hosseini K, Chalstrey E. 2023. [Ten simple rules for working with other people’s code](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1011031)。

## 执行

金标引用校验：

```powershell
.\.venv\Scripts\python.exe -m papertrail.gold --sources evals/pt15-heldout-sources.yaml --gold evals/pt15-heldout-gold-20261023.jsonl --minimum-questions 6
```

预登记提交后，首次且唯一模型运行：

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_pt15_model_e2e_once.py
```
