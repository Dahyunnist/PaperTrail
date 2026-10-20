# PaperTrail 交付与简历表述边界

## 本机 Web 演示

使用已创建的 `all-in-rag` Python 环境和本地模型缓存。PowerShell 启动命令：

```powershell
$env:PYTHONPATH = ".local/p6-runtime"
$env:HF_HUB_OFFLINE = "1"
$env:PAPERTRAIL_RETRIEVAL_MODE = "hybrid_bge_wide"
$env:PAPERTRAIL_EVIDENCE_LIMIT = "8"
Remove-Item Env:PAPERTRAIL_LLM_MODEL -ErrorAction SilentlyContinue
D:\Anaconda3\envs\all-in-rag\python.exe -m papertrail.web --db .local/papertrail-expanded-s1.sqlite3 --port 5055
```

打开 `http://127.0.0.1:5055`。在“你的问题”输入框问“TabDiff 的实验中 Trend 指标相对 TabSyn 提升多少？”。页面展示检索摘录、PDF 页码和 SHA 前缀；此演示配置不调用生成模型 API。停止演示时关闭启动服务的终端。

默认问答模式仍为 BM25、每题 5 条证据。`PAPERTRAIL_RETRIEVAL_MODE` 可选 `bm25`、`bge`、`hybrid_bge`、`hybrid_bge_wide`、`hybrid_bge_dense_rerank` 等已支持模式；`PAPERTRAIL_EVIDENCE_LIMIT` 范围为 1–8。环境值无效时模式回退到 BM25，证据数回退到 5。

## 可直接用于简历的表述

> 构建本地文献检索与证据约束问答原型，索引 62 篇去重 PDF；实现 BM25/BGE 混合检索、PDF 哈希/页码/引文校验、逐 claim 支持与覆盖审查，并交付 Flask Web 演示。P9 独立非盲评测覆盖 30 题：离线目标页 Recall@10 为 0.778；真实模型对 27 道可回答题作答 5 道，人工核查 4 道正确、1 道部分正确，22 道错误拒答；不可回答题正确拒答 3/3。

准确的能力边界：本地研究原型。P9 不是盲测，跨论文、冲突、多跳题未答出；结果不支持生产级质量、完整覆盖或泛化能力声明。P10 另有 12 题非盲小样本复验：可回答题仅 1 题正确，9 题错误拒答、1 题错误回答；不可回答题正确拒答 1/1。P10 未显示可答覆盖改善，不能并入 P9 指标。细节见 `docs/learning/stage-P9.md` 与 `docs/learning/stage-P10.md`，逐题审阅见 `evals/p10-human-review-20261020.json`。
