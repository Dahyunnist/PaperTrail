# PaperTrail

面向本地科研文献的可核查证据检索项目。核心设计是“证据账本 + 文献版本谱系”：每条答案论断最终要能回到具体文件版本、PDF 页码和短证据片段。

## 当前阶段

S0 已完成；当前执行 S1：文本 PDF/Markdown 解析与 SQLite FTS5 关键词检索。最终产品体验、证据边界与 S0–S5 阶段归属见 [产品契约](docs/product-contract.md)。

## 源资料

默认只读扫描 `configs/sources.example.yaml` 指定的目录。扫描只计算哈希与 PDF 页级文本统计，不复制或改写源文件。请先检查并按本机路径调整配置，再运行：

```powershell
python -m pip install -r requirements-dev.txt
python -m papertrail.audit --sources configs/sources.example.yaml --out docs/corpus-audit.md --inventory-out .local/corpus-inventory.jsonl
python -m pytest
```

`.local/` 盘点明细和本地检索数据库包含完整路径/全文，默认忽略且不应提交。`docs/corpus-audit.md` 保存可共享的统计摘要、路径说明和异常清单。PDF、全文抽取物、索引、模型缓存和密钥均不进入 Git。

## 阶段路线

1. S0：资料盘点、人工黄金集与基线设计。
2. S1：文本 PDF/笔记解析与 SQLite FTS5 关键词检索基线。
3. S2：混合召回、增量索引和 OCR；按黄金集、延迟、成本评测 MQE/HyDE 等候选。
4. S3：多轮证据问答、claim 级引文核验和拒答。
5. S4：跨论文比较、版本谱系与冲突对照。
6. S5：Web 学习助手、PDF 管理、个人笔记/回顾、进度和学习报告导出。

每阶段提交并等待确认后再进入下一阶段。
