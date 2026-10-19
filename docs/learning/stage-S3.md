# S3 学习记录：证据约束问答与 claim 校验

## 本阶段交付

CLI `ask` 将一个问题映射到已索引的原始 PDF，再生成由逐字原文摘录组成的结构化 claims。每条 claim 都带一条 EvidenceSpan：逻辑论文 ID、SHA 文件版本、PDF 物理页码、chunk ID、原文短句、解析器版本、来源路径和检索分。CLI `history` 根据 conversation ID 读取持久化多轮会话。

## 验证顺序

1. 问题只在来源类型 `original_pdf` 内搜索；个人笔记不会作为论据。
2. OCR 生成的 `ocr_derived` 块不进入 answer claims。
3. 每个候选引文重算源文件 SHA-256，确认与索引时的文件版本一致。
4. 确认引用页码在 PDF 物理页范围内，并重新抽取该页文字。
5. 规范化连字符换行和空白，再确认完整短句确实存在于所指页。校验失败的候选全部丢弃；没有剩余片段时拒答。
6. 保存问题、回答状态、检索模式、短期多轮上下文指针和 claims/evidence JSON；它们存于问答表，不写入论文 chunk 或个人笔记表。

## 回答策略

当前环境没有配置本地语言模型。为避免未经验证的自然语言综合，回答只表示“找到的已核验摘录”，并将每个 claim 限定为原文逐字引用。它不声称引用本身已经充分回答问题，也不把排序分解释成概率或可信度。基于关键词的句子相关性筛选会丢弃过于宽泛或截断的候选；找不到足够词面支持时返回 `abstained`。

这种策略牺牲了直接的中文解释体验，但保留了严格、可复核的引用闭环。之后若加入生成模型，必须将其输出拆成 claims，再逐条验证；原始模型回答不得直接展示为已证实结论。使用付费 API 前必须明确评估费用并取得用户批准。

## 多轮上下文

每个会话有独立 UUID 和时间戳。对很短的追问，系统将上一轮问题并入当前检索查询，并在响应中记录 `context_query`；回答和每条 evidence 仍各自从实际 PDF 检索、哈希核对和页内引用验证得出。历史读取只返回该 conversation ID 的 turns 与引用。

## CLI 与验证

```powershell
python -m papertrail ask --db .local/papertrail.sqlite3 --question "How does TabDDPM handle categorical data?"
python -m papertrail ask --db .local/papertrail.sqlite3 --question "And its columns?" --conversation-id <UUID>
python -m papertrail history --db .local/papertrail.sqlite3 --conversation-id <UUID>
```

`tests/test_s3.py` 使用合成 PDF 检查摘录精确匹配、SHA/页指针、多轮上下文和对源 PDF 篡改的拒答。当前阶段全量测试共 8 项通过，S0 黄金集 37 条原文短引文仍全部通过逐页核验。真实 pilot 上的 TabDDPM 询问展示两句来源于候选论文页的原文摘录；结果明确列出论文、页码、SHA 和排序分。

## 限制

- 当前不是生成式问答，也不自动比较、合并或推断多篇论文的立场。跨论文证据矩阵在 S4 处理。
- 页面相邻块排序和中文问题/英文原文词汇间隔会影响候选质量；每条 claim 的“已核验”只保证文本来自所指文件版本和页，不保证该片段完整回答了用户意图。
- 会话数据保存在本机 SQLite；当前没有登录或多用户授权层，运行在本机单用户边界内。

下一阶段按同一逻辑论文/版本/证据页结构整理跨论文支持、反对和适用条件，不将阅读笔记或 OCR 产物升级为论文事实。
