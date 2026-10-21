# PaperTrail

面向本地科研文献的可核查证据检索项目。核心设计是“证据账本 + 文献版本谱系”：每条答案论断最终要能回到具体文件版本、PDF 页码和短证据片段。

## 当前阶段

S0–S5 已完成。最终产品体验与证据边界见 [产品契约](docs/product-contract.md)；各阶段记录见 [S0](docs/learning/stage-S0.md)、[S1](docs/learning/stage-S1.md)、[S2](docs/learning/stage-S2.md)、[S3](docs/learning/stage-S3.md)、[S4](docs/learning/stage-S4.md)和 [S5](docs/learning/stage-S5.md)。

## 源资料

默认只读扫描 `configs/sources.example.yaml` 指定的目录。扫描只计算哈希与 PDF 页级文本统计，不复制或改写源文件。请先检查并按本机路径调整配置，再运行：

```powershell
python -m pip install -r requirements-dev.txt
python -m papertrail.audit --sources configs/sources.example.yaml --out docs/corpus-audit.md --inventory-out .local/corpus-inventory.jsonl
python -m pytest
```

`.local/` 盘点明细和本地检索数据库包含完整路径/全文，默认忽略且不应提交。`docs/corpus-audit.md` 保存可共享的统计摘要、路径说明和异常清单。PDF、全文抽取物、索引、模型缓存和密钥均不进入 Git。

可将 `.env.example` 复制为 `.env` 配置可选生成模型；本机 Ollama 无需 API 密钥。不要提交 `.env` 或文献盘点产物。

## 阶段路线

1. S0：资料盘点、人工黄金集与基线设计。
2. S1：文本 PDF/笔记解析与 SQLite FTS5 关键词检索基线。
3. S2：本地向量候选、BM25/RRF 检索与增量向量索引；OCR 作为可选回退。
4. S3：证据约束回答、claim 级引文核验和拒答。
5. S4：跨论文比较、版本谱系与冲突对照。
6. S5：Web 学习助手、PDF 管理、个人笔记/回顾、进度和学习报告导出。

每阶段形成独立 Git 提交，提交 message 使用中文。

检索命令支持 `--mode bm25|vector|hybrid|bge|hybrid_bge|hybrid_bge_wide|hybrid_bge_rerank`；LLM rerank 需要配置 OpenAI-compatible model。页面排序实验可用 `python -m papertrail.evaluate --compare --modes hybrid_bge_wide hybrid_bge_rerank ...`。当前保持默认 `bm25`。需要重建潜在向量索引时使用 `python -m papertrail vector-build`。可用 `python -m papertrail index --ocr-fallback ...` 对低文本 PDF 页尝试本机 Tesseract OCR；OCR 文本会标为派生内容，不可直接作为引用。

只读 MCP stdio 服务可用 `python -m papertrail mcp --db .local/papertrail.sqlite3` 启动。提供 `search_papers`、`get_evidence`、文献元数据资源和原文页资源；证据调用会重新校验 PDF SHA-256。个人笔记不会进入 MCP 搜索。

可选本机生成需先启动本机 Ollama 并准备模型，再设置 `PAPERTRAIL_LLM_MODEL`；服务只连接 `PAPERTRAIL_OLLAMA_URL`（默认 loopback `http://127.0.0.1:11434`），没有云端回退。生成 claim 会引用已校验的原文页，并经本机模型逐条审查；模型不可用或没有支持证据时拒答。请把 LLM 支持性判断视为审查信号，不等同于人工核验。

QA 轨迹默认存于本机 SQLite。人工评分用 `python -m papertrail trajectory-rate --db .local/papertrail.sqlite3 --turn-id <turn-id> --rating correct`，可选 `--note` 记录理由；导出用 `python -m papertrail trajectory-export --db .local/papertrail.sqlite3 --out .local/trajectories.jsonl`。导出含问题、回答、引用指针和用户评分，应按本机研究数据管理。

S3 使用 `python -m papertrail ask --db .local/papertrail.sqlite3 --question "你的问题"` 获取经 SHA、页码和原文校验的摘录；通过返回的 `conversation_id` 传给后续 `ask --conversation-id ...` 保留短上下文，或使用 `history --conversation-id ...` 回顾。当前没有配置生成模型，因此 S3 只给出可核验摘录，不自动撰写综合答案。

S4 使用 `python -m papertrail compare --db .local/papertrail.sqlite3 --topic "主题" --claim "待比较论断"` 收集并列原文；通过 `compare-label` 逐条标记 `supports|contradicts|conditions|context|unclear`，也可通过 `compare-gap` 记录用户提出、待复核的研究空白候选。`compare-report` 汇总标注和证据。

启动最终工作台：`python -m papertrail web --db .local/papertrail.sqlite3 --sources configs/sources.example.yaml --selection configs/s1-pilot.jsonl`，再打开 `http://127.0.0.1:5000`。页面可更新明确选择的授权文献、上传/删除个人 PDF、问答、创建隔离的个人笔记、标注跨论文证据并导出 JSON 学习报告。服务仅监听本机；所有工作数据保存在 `.local/`。
