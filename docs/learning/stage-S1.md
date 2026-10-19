# S1 学习记录：文献解析与 FTS5 检索基线

## 本阶段的目标

把 S0 的只读目录盘点和人工黄金集接到一个可复建的本机索引上。每条检索结果都能返回原文件哈希、来源类型、相对/绝对来源路径、PDF 物理页码、章节、原始文本块和排序分；原文 PDF 与中文阅读笔记从索引到结果都分开标记。

## 当前数据流

```mermaid
flowchart LR
  A[授权根目录配置] --> B[明确选择清单与 SHA 校验]
  B --> C[PDF 或 Markdown 解析]
  C --> D[论文候选与 SHA 文件版本]
  C --> E[章节父文本与页内子块]
  D --> F[SQLite 元数据]
  E --> G[SQLite FTS5 BM25]
  H[中文问题/英文关键词] --> G
  G --> I[排序结果、来源类型、PDF 页码、短文本]
  J[人工黄金集] --> K[Recall@5 与逐题轨迹]
  I --> K
```

## 解析和身份设计

- `papertrail/s1_index.py` 读取文本型 PDF 的页文本与版面块，尽量按字体、编号和短标题识别章节；Markdown 以标题建立章节。每个 PDF 块保留物理页码，长段切成最多 1800 字的子块，同时保留所属章节父文本。
- PDF 题名复用 S0 候选规则，剔除会议横幅等封面噪声。DOI 只从首页附近提取为候选。当前逻辑论文 ID 由唯一 DOI 或规范化题名产生，状态仍标记 `provisional`；SHA-256 才确定具体 `PaperVersion`。它尚未实现经过人工确认的复杂版本谱系。
- 字节相同的 PDF 仅索引一份，但记录多条源路径；不同 SHA 文件各自保留版本记录。个人阅读梳理标记 `reading_note`，不会显示成 PDF 页或原文证据。
- SQLite 数据库存于 `.local/`。`configs/s1-pilot.jsonl` 以来源根 ID、相对路径、文件名和 SHA 明确选择 pilot，重跑时校验路径仍在授权根目录中且文件哈希一致。

## CLI 使用

```powershell
python -m papertrail index --sources configs/sources.example.yaml --selection configs/s1-pilot.jsonl --db .local/papertrail.sqlite3
python -m papertrail search --db .local/papertrail.sqlite3 --query "TabDDPM categorical diffusion" --limit 5
python -m papertrail inspect --db .local/papertrail.sqlite3 --document <SHA前缀>
python -m papertrail status --db .local/papertrail.sqlite3
python -m papertrail.evaluate --db .local/papertrail.sqlite3 --gold evals/gold.jsonl --k 5 --trace-out .local/s1-retrieval-trace.json
```

搜索展示 BM25 分数、来源类型、标题、章节、SHA、路径、页码与命中片段。分数只是排序值，不能解释成概率或论断可信度。查询以英文关键词为主；正文 AND 无结果时放宽到 OR。笔记可单独检索或筛除。

## 评测结果和解释

S1 pilot 选择了 12 篇原文 PDF（覆盖 10 篇黄金集来源文献并增加 2 篇相关论文）及 3 篇中文阅读笔记。34 道黄金题中 31 道可回答。当前 top-5 命中目标论文 28/31（90.3%）；命中至少一条标注目标 PDF 证据页 10/31（32.3%）。完整逐题结果和版本信息写入本机 `.local/s1-final-trace.json`，没有把全文或本机路径提交到 Git。

这是有用但有限的基线：检索常能找到对的论文，却很难仅凭中文问句把结果压到人工核验的具体页。尤其不能把“论文命中”当作“证据定位成功”。S2 需要用相同问题集对照 dense/hybrid 等方法及题型分组，核查错页和跨文献干扰，并记录延迟、资源成本与实际收益；不应以更复杂的检索组件本身作为成功标准。

## 验证与限制

- `python -m pytest -q`：6 项通过。测试覆盖 SHA 重复去重、多路径保留、不同版本、笔记隔离、DOI/术语和第二页定位、表格文本保留、元数据封面噪声过滤。
- 本阶段不含 OCR、向量索引、重排、LLM 问答、Web 界面或用户上传。扫描型 PDF 可能只有低文本页标记，没有可用内容。表格目前以抽取文本保存，尚未验证行列关系。
- 评测使用当前小型 pilot 和黄金问题，不是端到端用户答案质量测试；查询、题目与结果仍需人工核验。

## 与最终产品的关系

最终本机 Web 学习助手、笔记/问答记忆边界和 S0–S5 阶段责任见 [产品契约](../product-contract.md)。S1 只建立文本解析和可追溯关键词检索基础；Web 学习闭环属于 S5。Datawhale 8.4 的文档问答、概念笔记、学习回顾和进度报告被吸收为目标体验，MQE、HyDE 及多层记忆仍须通过本项目黄金集评测后再决定。
