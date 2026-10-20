# 阶段 P11：提示预算与证据校验修复

日期：2026-10-20

## 本阶段发现

P11 首轮使用真实 DeepSeek API 检查了 6 道本地文献问答。它是维护者阅读语料后编写的非盲诊断集，不能代表一般问答质量。

首轮 5 道可回答题中只有 2 道得到经审查回答。轨迹显示，检索筛选调用成功，但后续合成提示超过 DeepSeek 客户端的 2,400 字符硬上限，系统因此安全拒答。继续追踪后，还发现 PDF 分行断词会令已核验原文被错误判为不匹配，例如 `in- ference` 与 PDF 中的 `inference`。

P12 首轮还暴露了指标型提问的边界：模型可能把“检索片段没有给出精确值”说成“文献没有报告”，并可能从语料中的另一篇论文取到相似设备信息。

## 已做修复

1. 筛选、生成、复核提示统一按序列化后的字符数收缩，目标上限为 2,200 字符，为客户端追加字段预留余量。收缩时先移除低位证据，再缩短摘录；保留原证据 ID。
2. 对 DeepSeek 非思考模式显式设置 `temperature=0.0`，减少默认温度带来的输出波动。API 文档说明默认值为 1.0，低温输出更集中。[DeepSeek Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/)
3. 证据归一化改为合并行尾连字符和换行空白，避免 PDF 排版断词破坏逐页引文验证。
4. 问题要求 GPU 序列号时，只有已核验证据明确包含序列号和值才继续回答；只看到 GPU 型号时直接拒答，并在轨迹中记录拒答阶段。
5. `requirements-dev.txt` 补上 MCP 测试所需的官方 SDK 依赖。

## 验证

- 针对提示预算、行尾断词、序列号守卫和既有 QA 路径新增回归测试。
- P12 的 5 条可回答题证据短引文均通过原 PDF 哈希、页码和文本核验；拒答题不附支持性引文。
- DeepSeek `deepseek-flash` 在 P12 上实际调用 20 次，估算成本 `$0.004953`。5 道可回答题中 4 道完成回答，完整回答率 `4/5`；序列号题正确拒答 `1/1`。
- P12 精确 gold 页命中 `3/5`，引文精度 `0.818`，被审查接受的生成主张 `11/14`。不同运行结果有波动；本轮仍有 1 道可回答题拒答，且并非盲测。
- 本机账本累计上界 `$0.2549562`，项目预算上限 `$0.50`。没有提交 API 密钥、账本、私有文献片段或本地 P12 题集。
- 全套回归结果以最终执行记录为准；MCP 子进程测试需在可导入 MCP 与 PyMuPDF 的 Python 环境执行。

## 还不能声称

P12 只有 6 题，且维护者查看过语料与先前输出。它只能证明几项明确缺陷已被复现并修复，不能证明 RAG 对其他文献、复杂问题或未见用户问题已经稳定。抽取式基线会返回摘录，不应把它的“覆盖率”当成正确生成率。

## 复现入口

在具备项目依赖的 Python 环境中运行全套测试：

```powershell
python -m pytest -q
```

重新运行本地真实模型诊断前，确认 `DEEPSEEK_API_KEY` 已由本机环境提供，并在项目目录执行：

```powershell
$env:PAPERTRAIL_LLM_PROVIDER = 'openai-compatible'
$env:PAPERTRAIL_LLM_MODEL = 'deepseek-flash'
$env:PAPERTRAIL_LLM_BUDGET_USD = '0.50'
python -m papertrail.evaluate_qa --db .local/papertrail-expanded-s1.sqlite3 --gold .local/p12-gold-20261020.jsonl --out .local/p12-evaluation.json --minimum-questions 6
```

P12 与语料数据库均在 `.local/`，不会进入 Git。只有在本机存在相同的本地语料库时，上述模型评测命令才可复现。
