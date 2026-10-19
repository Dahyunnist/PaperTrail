# PaperTrail

面向本地科研文献的可核查证据检索项目。核心设计是“证据账本 + 文献版本谱系”：每条答案论断最终要能回到具体文件版本、PDF 页码和短证据片段。

## 当前阶段

S0–S2 已完成；当前执行 S3：受检索证据约束的问答和引用核验。最终产品体验、证据边界与 S0–S5 阶段归属见 [产品契约](docs/product-contract.md)。

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
3. S2：本地向量候选、BM25/RRF 检索与增量向量索引；OCR 作为可选回退。
4. S3：证据约束回答、claim 级引文核验和拒答。
5. S4：跨论文比较、版本谱系与冲突对照。
6. S5：Web 学习助手、PDF 管理、个人笔记/回顾、进度和学习报告导出。

每阶段形成独立 Git 提交，提交 message 使用中文。

检索命令支持 `--mode bm25|vector|hybrid`；需要重建潜在向量索引时使用 `python -m papertrail vector-build`。可用 `python -m papertrail index --ocr-fallback ...` 对低文本页尝试本机 Tesseract OCR；OCR 文本会标为派生内容，不可直接作为引用。
