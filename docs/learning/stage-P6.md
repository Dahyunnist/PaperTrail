# P6 学习记录：真实模型验收

## 冻结题集

冻结文件：`evals/p6-gold-20261020.jsonl`。SHA-256：`044546cf3745edc4eae6ab6c14d8ff73676e2d91bb656fbd6b21ea4ac178f6e1`。共 34 题、37 条证据指针、10 篇被引用论文；索引库含 12 篇原论文 PDF。题型：事实定位 20、方法比较 5、跨论文 2、多跳 1、冲突 3、不可回答 3。清单见 `evals/p6-manifest.json`。

三个 `conflict` 题检查不同实验设置下的结论冲突，不是同一论文的多个文件版本。当前 12 篇来源 SHA 均唯一，缺少真实多版本论文对；版本冲突能力尚未单独验收。

## 模型、数据边界和费用

使用本机已有的 `DEEPSEEK_API_KEY`，直连官方 OpenAI-compatible endpoint，模型 `deepseek-flash`。主机没有 Ollama 和生成权重。API 只收到黄金题问题、最多 650 字符的证据上下文、短标题和页码。不会发送 PDF、本机路径、个人笔记或密钥。语料选自科研论文，不含用户私人材料。

本机预算账本 `.local/p6-api-usage.json` 不记录 prompt 或密钥。每次请求发送前按官方峰值价估算输入和输出，并保守按每字符 4 tokens、每次最多 320 个输出 tokens 预留。总上限固定 `$0.19`，不能用环境变量调高；达到上限即拒绝发送。无自动重试。

截至 2026-10-20，官方价格页列出 Flash 峰值 cache-miss 输入 `$0.30/百万 tokens`、输出 `$1.20/百万 tokens`。预算也按这组较高峰值计算；价格会变化，运行前应复核[官方价格表](https://api-docs.deepseek.com/quick_start/pricing/)。请求格式按[官方 Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/)执行。

整次 P6 包含 39 个请求。账本估算上界 `$0.01053`，低于 `$0.19`。34 题对照本身累计 8,774 输入 tokens、3,591 输出 tokens，费用上界 `$0.0069414`。没有 request prompt、密钥或完整原文落盘。

## 结果

相同 `hybrid_bge` 检索下，抽取式是“证据摘录存在即返回”，不能当作答案正确率。生成式只有每条 claim 经过真实 API 支持性审查后才显示。

| 指标 | 抽取式 | 生成式 + claim 审查 |
|---|---:|---:|
| 31 道可答题有输出 | 29/31（93.5%） | 2/31（6.5%） |
| 命中黄金证据页 | 7/31（22.6%） | 1/31（3.2%） |
| 3 道不可答题正确拒答 | 1/3（33.3%） | 3/3（100%） |
| 不可答题错误输出 | 2/3（66.7%） | 0/3（0%） |
| 平均端到端时延 | 2,604 ms | 4,051 ms |

生成式输出只有 3 个引用：1/3 命中黄金目标页。真实 SHA、页码和摘录均通过本机 PDF 核验；这证明引用确实来自文件，不证明它回答了问题。

## 人工复核

人工检查了全部两道有生成 claim 的题、被 claim judge 拒绝的 claim，以及三道拒答题。S0-017 引用页正确，但回答只写 `Domain transfer`，漏掉黄金答案中的 `utility`。S0-022 的两条 claim 和引用页 38 在字面上有支持，claim judge 接受；但题目问不同 label-noise 下观察，黄金答案为“持续提升效用”，该回答转述相邻背景、未回答问题，也未命中目标页 10。这是实际错答，不是引用伪造。

三道不可回答题均拒答。三个跨论文/方法冲突类别的问题全拒答，显示系统过度保守。多数可答题因证据候选不准或 claim 输出为空而拒答。现有 claim judge 只检查引用是否支持 claim，不检查 claim 是否回答用户问题；必须补 relevance/coverage 审查和更好的证据页召回。

## 可复现命令与结论

```powershell
$env:PAPERTRAIL_LLM_PROVIDER = "openai-compatible"
$env:PAPERTRAIL_LLM_MODEL = "deepseek-flash"
$env:PAPERTRAIL_OPENAI_API_KEY_ENV = "DEEPSEEK_API_KEY"
$env:PAPERTRAIL_LLM_BUDGET_USD = "0.19"
python -m papertrail.evaluate_qa --db .local/papertrail-s1-final.sqlite3 --gold evals/p6-gold-20261020.jsonl --out .local/p6-qa-comparison.json --mode hybrid_bge
```

API endpoint 默认限定为官方 DeepSeek 服务；只有原论文来源进入检索，reviewer 不接收本机路径。完整请求成本、token 计数和结果保存在忽略目录 `.local/`。全量 19 项测试通过。

这轮证明真实生成/审查线路可运行，也量出较低覆盖率、低页命中和长延迟。结果不达简历中的“可信生成式 RAG”门槛。P7 先修复召回并做 rerank 消融，再重跑冻结集。
