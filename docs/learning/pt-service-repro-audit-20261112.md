# S4/S5 服务与复现审计（2026-11-12）

## PT1 标注状态

只统计 CSV 字段，不读取 PDF：5 条最小模板为 **0/5** 已标注、**0/5** 双人复核；40 条模板为 **0/40** 已标注。每条已有候选问题、DOI、PDF SHA-256 和候选章节页提示；gold 引文、证据页、答案、标注人与复核人仍为空。不得把候选章节页提示当作证据页，也不得把题目改写建议当作人工答案。引文与物理页必须由标注者在原 PDF 内核验。

最小 5 条任务位于 `evals/pt1-human-annotation-task-5-20261111.csv`：PT1-H001 至 PT1-H005。CSV 已含每题 candidate question 和 PDF SHA；`candidate_basis_pdf_page` 只是章节线索。标注者需补最短完整原文 span、真实 PDF 页、字符范围、答案与答题性；第二人核验原 PDF 并填 reviewer、review_status。导入前先做任务结构校验：

```powershell
.\.venv\Scripts\python.exe scripts/validate_pt1_human_annotation_task.py
```

双人完成后再运行 CSV 一键导入；它会核对来源 SHA、PDF 页和精确 span，并要求最少 5 题、5 篇论文：

```powershell
.\.venv\Scripts\python.exe scripts/import_pt1_human_csv.py evals/pt1-human-annotation-task-5-20261111.csv --min-questions 5 --min-papers 5 --output-v2 .local/pt1-human-gold-v2.jsonl --output-gold .local/pt1-human-gold-runtime.jsonl --output-sources .local/pt1-human-sources.yaml
```

当前运行会因标注字段为空而拒绝；没有伪造答案或引文。

## S4/S5 复现状态

README 所列 S4 CLI 子命令 `compare`、`compare-label`、`compare-gap`、`compare-report` 均存在；S5 `web` 和只读 `mcp` 入口存在。五分钟演示引用的 PT3 synthetic source config、gold 和 report 文件均存在。页面服务只监听 loopback，测试通过 Flask test client，不启动外部服务，不访问配置来源。

定向离线 smoke：`tests/test_access_control.py`、`tests/test_s5_web.py` 和 `tests/test_service_repro.py`，使用临时数据库与合成 PDF，覆盖 Web 首页、搜索 API、无效证据响应、上传索引学习闭环与 README 入口一致性。运行前清空模型变量：

```powershell
$env:PAPERTRAIL_LLM_MODEL = ''
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .tmp/pytest-pt-service tests/test_access_control.py tests/test_s5_web.py tests/test_service_repro.py
```

测试不读取 `.env`、私人 PDF、私有来源清单或 `.local` 索引，也不调用模型。公开 synthetic demo 的逐页校验命令仅访问 `evals/fixtures/pt3-synthetic/` 下合成 PDF。

## 边界

服务 smoke 证明当前 CLI 路由和本机 Web 合成流程可运行，不证明生产部署、并发容量、真实来源权限配置或真实文献 QA 质量。PT1 人工 gold 仍未通过用户关口。
