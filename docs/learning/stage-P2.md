# P2 学习记录：本机 claim 综合与记忆隔离

## 实现

增加 Ollama-compatible loopback JSON 客户端。只有设置 `PAPERTRAIL_LLM_MODEL` 才会调用；默认不连接云端，也不自动下载模型。将已通过 PDF 哈希、页码和文本校验的证据作为有限上下文传入本机模型，要求返回原子 claim 与证据编号。随后用单独的审查请求逐条判断引用是否支持 claim。缺引用、错编号、JSON 不合法、审查结果缺失或模型故障都会拒答。只保留审查返回 `supported=true` 的 claim。

每条生成 claim 保存引用原文、支持证据和 `local_llm_judge` 审查方法。上下文最多约 12,000 字符，每篇摘录不超过 700 字符。上传 PDF 若哈希变化，原有校验会拒绝使用旧版本证据。

个人笔记与 QA 轮次保存在独立表。QA 检索限定原论文来源；短追问只读取同一 `conversation_id` 的上一问题。不同对话不会共享短期记忆。个人笔记不会自动注入回答上下文。

## 实测边界

当前主机没有 Ollama 命令、运行服务或生成模型权重。因此没有实跑生成/审查模型，不能报告回答准确率、tokens 或生成时延。测试验证 loopback HTTP 协议、证据边界、注入失败关闭、claim 引用编号与支持状态过滤。`local_llm_judge` 是模型判定记录，不是形式化蕴含证明，也不能替代人工审核。

## 验证

```powershell
python -m pytest tests/test_local_llm.py tests/test_s3.py -q
python -m pytest -q
```

本阶段全量 16 项测试通过。要得到真实模型结果，先准备本机 Ollama 模型，再设置 `PAPERTRAIL_LLM_MODEL` 和可选的 `PAPERTRAIL_OLLAMA_URL`，运行同一黄金集与人工标注评审。

## 经验

RAG claim 应拆开生成和支持性检查，并保存具体引用。引用真实存在不代表 claim 被引用支持。模型裁判能筛掉明显越界回答，但仍可能误判；产品必须保留逐条原文与审查方法供读者复核。
