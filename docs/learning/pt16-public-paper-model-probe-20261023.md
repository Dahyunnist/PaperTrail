# PT16 开放论文单题真实生成探针

## 预登记

- 来源：《Good enough practices in scientific computing》，DOI `10.1371/journal.pcbi.1005510`。PLOS 页面确认文章按 CC BY 4.0 发布；来源 PDF 已登记并核对 SHA-256。只向模型发送检索到的一条短证据，不发送私人论文或整篇 PDF。
- 新题：`Where should researchers put input data versus files produced during analysis?`
- 可核验 oracle：原文 PDF 第 10 页说明原始数据与元数据放在 `data` 目录，清理与分析生成的文件放在 `results` 目录；生成文件包括中间与最终结果。
- 生成 claim 逐条对照以上三项；引用须符合预期页码、PDF 哈希，并在对应原文页逐字存在。模型内审不算独立语义审查。
- 不读取或改动 PT15、PT9、PT12 的 gold、题集或评测结果。

## 费用门禁

DeepSeek 官方价格页的峰值单价为输入 `$0.30/M`、输出 `$1.32/M`。按每次最多 2,400 输入字符、每字符最多 4 token、最多 800 输出 token，单请求最坏预留 `$0.003936`。最多 8 次调用，包含筛选、生成、重试和审查，模型预留总额 `$0.031488`；收尾缓冲 `$0.008512`，阶段硬上限 `$0.04`。

调用前主账余额 `$0.06643472`。阶段最多花费 `$0.04` 后，至少保留 `$0.02643472`。任何 prompt 超长、请求次数超限、账本不足或检索片段校验失败，都会在发送前拦截。

## 复现

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe scripts/evaluate_pt16_public_probe.py
.\.venv\Scripts\python.exe scripts/evaluate_pt16_public_probe.py --run-once
```

默认 dry-run 只导入该单篇许可明确的 PDF、执行 BM25 检索、核验引文并列出费用预留。真实运行只允许一次，结果文件存在时拒绝重跑。运行后按报告里的可见 oracle 人工核对 claim；不将模型自审称为独立标注，也不从单题推断基准准确率。

## 来源

- 论文与许可：[PLOS 文章页](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005510)、[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。
- 价格：[DeepSeek 官方模型价格](https://api-docs.deepseek.com/quick_start/pricing/)。
- 预登记：[pt16-public-probe-prereg-20261023.json](../../evals/pt16-public-probe-prereg-20261023.json)。
