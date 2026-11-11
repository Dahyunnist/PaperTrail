# PT-1 人工标注任务指南

## 任务包

- 任务表：`evals/pt1-human-annotation-task-40-20261111.csv`
- 来源清单：`evals/pt1-candidate-manifest-20261111.json`
- 离线生成器：`scripts/build_pt1_human_annotation_task.py`
- 表结构校验器：`scripts/validate_pt1_human_annotation_task.py`
- 人工 gold 格式：`evals/pt1-human-gold-schema-v2.json`
- PDF 引文校验器：`scripts/validate_pt1_gold_jsonl.py`
- 5题起步表：`evals/pt1-human-annotation-task-5-20261111.csv`

任务表含40个候选问题，覆盖30个不同 DOI。每篇至少一个单篇问题；另有10个问题从10篇论文的第二个规则标题生成，用来探测文中是否报告对应的量化效果。候选问题由本地 PDF 标题/规则标题确定性生成，不含模型输出。`candidate_basis` 和 `candidate_basis_pdf_page` 只说明候选题从哪里提出；不是证据标注。

所有论文都属于 `development_seen`，来源并非盲集。候选题需要人工审核、必要时改写或删除。问题只能针对该行 DOI，不得拼接其他论文信息。

## 标注字段

复制原始 CSV 到单独工作副本，再填写。保留原始模板不变，以便校验和复现。

- `answerability`：填 `可答`、`不可答` 或 `歧义`。逐项检查问题中的每个要求。只有论文原文能直接支持全部要求，才标可答。缺少关键事实标不可答；问法有多种合理解释时先标歧义并改写。
- `question_type`：填 `fact_location`、`method_comparison`、`cross_paper`、`multi_hop`、`conflict` 或 `unanswerable`。本 CSV 每题限一篇论文，优先使用 `fact_location`；不要把跨论文题硬塞进单篇题行。
- `expected_answer`：用简短答案响应候选题；不可答题填写明确的拒答依据，不猜测论文外事实。
- `minimal_complete_evidence_quote`：逐字抄录支撑答案所需的最小完整引文。若要多处证据，把引文写作 JSON 字符串数组。
- `evidence_pdf_pages`：填一基 PDF 物理页码；多处引文用 JSON 整数数组，顺序与引文一致。不要用页面印刷编号替代 PDF 物理页码。
- `original_pdf_excerpt`：逐字记录每处引文所在的原文上下文；多处用 JSON 字符串数组。保留符号、单位、否定词和小数点。
- `span_start_char`、`span_end_char`：按 PyMuPDF `page.get_text("text")` 原始页文本的 Unicode 字符索引填写，0 起点、右端不包含。多个引文在 `notes` 中以 JSON 数组记录对应 span；如解析文本无法稳定定位，留空并在备注说明，不能伪造。
- `annotator`、`reviewer`：填写真实参与者身份。标注者与复核者不能相同。
- `review_status`：复核前填 `未复核`；复核后填 `通过` 或 `退回`。退回时在 `notes` 写明具体问题。

不可答题的证据字段可以为空，但 `expected_answer` 必须写明确的拒答理由。不要用单处引文证明“全文没有”；人工需检查全文及问题涉及的章节范围。`歧义`题不得进入 gold，先改写再由两人重新标注。

### 多文献关系与答案判定

- 每条证据的 `relation` 标为 `supports`、`contradicts` 或 `context`。只在引文直接支持答案时标支持；原文直接给出相反结果时标冲突；背景信息标上下文。
- `cross_paper`、`method_comparison`、`multi_hop` 至少引用两篇不同 DOI，且每个结论部分都要有对应证据。比较方法时写清比较维度，不把不同条件下的结果说成矛盾。
- `conflict` 必须至少有两篇论文，并同时有支持与冲突关系。记录两篇研究的条件、对象或测量差异；证据不足以判断时改成不可答。
- 最小完整证据集合须覆盖答案每个必要事实。删掉其中任一条便无法核验对应事实，才算最小；页码按 PDF 物理页，从1开始。引用必须逐字符匹配该页 `get_text("text")`，span 为 Unicode 字符索引，左闭右开。
- 评模型回答时分开记录正确性与完整性：所有必要事实均被支持且无关键遗漏，判完整正确；已答部分有证据支持，但漏掉一个或多个必要项，判部分正确；关键内容无证据或与来源相反，判错误。对不可答题，明确拒答且理由正确才算正确拒答；猜答或对可答题错误拒答都算错误。

### 格式示例（虚构，不是 gold）

以下 DOIs、页码、引文和答案都是虚构格式示例。不能复制进任务表或 gold；也不能通过真实清单校验。

```jsonl
{"id":"EXAMPLE-1","paper_ids":["10.0000/fiction-a"],"split":"development","question_type":"fact_location","question":"示例研究报告了多少样本？","expected_answer":"报告了12个样本。","answerability":"answerable","evidence":[{"doi":"10.0000/fiction-a","pdf_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","pdf_page":2,"start_char":10,"end_char":31,"quote":"共纳入12个虚构样本。","relation":"supports"}],"minimumCompleteEvidenceSet":true,"annotation_status":"human_verified","annotator":"标注者甲","reviewer":"复核者乙"}
{"id":"EXAMPLE-2","paper_ids":["10.0000/fiction-b"],"split":"development","question_type":"unanswerable","question":"虚构论文是否报告了十年随访结果？","expected_answer":"不可答：已检查全文，论文未报告十年随访结果。","answerability":"unanswerable","evidence":[],"minimumCompleteEvidenceSet":true,"annotation_status":"human_verified","annotator":"标注者甲","reviewer":"复核者乙"}
{"id":"EXAMPLE-3","paper_ids":["10.0000/fiction-c","10.0000/fiction-d"],"split":"development","question_type":"conflict","question":"两项虚构研究对同一指标报告了什么结果？","expected_answer":"研究C报告上升，研究D报告下降；研究条件不同，不能合并成单一结论。","answerability":"answerable","evidence":[{"doi":"10.0000/fiction-c","pdf_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","pdf_page":3,"start_char":4,"end_char":18,"quote":"虚构指标上升。","relation":"supports"},{"doi":"10.0000/fiction-d","pdf_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","pdf_page":4,"start_char":5,"end_char":19,"quote":"虚构指标下降。","relation":"contradicts"}],"minimumCompleteEvidenceSet":true,"annotation_status":"human_verified","annotator":"标注者甲","reviewer":"复核者乙"}
```

## 抽样与冻结

任务表固定30篇 DOI、40题：30题按来源覆盖，10题是量化效果边界探测。所有题按 DOI 隔离。人工审阅时可替换不合格候选，但保持至少30篇不同 DOI、总计至少40题，并记录每次替换和理由。

冻结前逐题复核来源 DOI 与 PDF SHA-256、可答性、答案、最小完整证据集合、页码和原文摘录。每道题由第二人独立核对；退回题修订后再次复核。最终仅在两人确认后，把通过题写入 PT-1 gold JSONL，并更新 gold 哈希和清单版本。原始模板的所有标注字段必须继续为空。

## 运行校验

```powershell
.\.venv\Scripts\python.exe scripts/build_pt1_human_annotation_task.py
.\.venv\Scripts\python.exe scripts/validate_pt1_human_annotation_task.py
```

校验器要求40行、30个 DOI、字段结构匹配、来源哈希一致，且答案、可答性、引文、页码、摘录和复核字段全部留空。它校验模板，不校验人工填写后的副本。

填写时复制 CSV 到个人工作副本；先完成 `PT1-H001` 至 `PT1-H005`，请第二人复核，再继续其余题。保留原模板不变。整理为 JSONL 后运行：

```powershell
.\.venv\Scripts\python.exe scripts/validate_pt1_gold_jsonl.py <人工gold.jsonl路径>
```

5题先使用上述独立 CSV 工作副本；其内容对应40题总表的 `PT1-H001` 至 `PT1-H005`，不要把答案写回空白总表。每题先核查候选问法，再填题型、可答性、答案/拒答理由、最小完整引文、PDF 物理页码、原文上下文、字符 span、标注者和复核者。复核者独立核对来源 PDF 后，才把状态记为 `通过`。保留 DOI 与原 PDF SHA，不要把格式示例当答案。

转换为 PT1 v2 JSONL 后，可先校验5题：

```powershell
.\.venv\Scripts\python.exe scripts/validate_pt1_gold_jsonl.py <人工gold.jsonl路径> --min-questions 5 --min-papers 5
```

校验器能核对重复题、双人复核、回答/拒答结构，以及清单中的 PDF SHA、物理页码和逐字符引文 span。它不读取 CSV；从 v2 JSONL 转为运行时格式的步骤见下节。当前 PT1 gold 0/40，PT1 与依赖它的真实论文 PT3 评测均未完成；不要用空集或合成示例报告质量指标。

### 导入运行时 gold

CSV 仍需人工整理为 v2 JSONL；导入器不替人推断或补标字段。导入会先执行 v2 校验，再转换为旧运行时结构，并调用 `papertrail.gold.load_gold` 与 `verify_quotes` 二次校验。未复核、字段不全、答案/拒答不匹配、PDF 哈希/页码/span/引文不符或题数不足时，不生成输出。跨文献题型、拒答标记和引文关系保留。

5题复核通过后运行：

```powershell
.\.venv\Scripts\python.exe scripts/import_pt1_gold_jsonl.py <人工gold-v2.jsonl路径> --output-gold .local/pt1-human-gold-runtime-5.jsonl --output-sources .local/pt1-human-sources-5.yaml --min-questions 5 --min-papers 5
```

40题完整批次使用默认门槛，不要传5题门槛。`.local` 输出含本机 PDF 根路径，只保存在本地。导入成功只表示人工记录通过结构和引文校验；不代表模型评测已运行或达到指标。
