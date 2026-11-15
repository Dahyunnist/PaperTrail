# S5 学习记录：本机 Web 学习工作台

## 产品闭环

`python -m papertrail web --db .local/papertrail.sqlite3 --sources configs/sources.example.yaml --selection configs/s1-pilot.jsonl --allow-local-dev-principal` 启动本机 Flask 演示页面，绑定 `127.0.0.1`，默认端口 5000。演示开关明确启用固定 `local-dev` Principal；不带该开关时必须由服务端 `PRINCIPAL_PROVIDER` 提供有效 Principal，否则返回 401。客户端 header、query 或 body 不会设定身份。页面提供：

- **文献库**：刷新明确选择的授权文献；查看题名候选、版本 SHA、来源类型、页数、解析状态、低文本页和配置来源；上传 PDF 并查看处理状态；删除个人上传。
- **原文问答**：连续追问，回看会话；每条 claim 展示逐字短引文、来源论文、PDF 页、SHA 前缀和相关性排序值；无可核验证据时明确拒答。
- **个人笔记**：按概念保存、关键字检索和删除。笔记在 `personal_notes` 单独存储，不进入 `chunks`、FTS 或论文答案证据。
- **跨论文对照**：收集不同论文候选句，逐条人工标记支持、反对、适用条件、背景或不清楚，并记录理由；用户可以提交待复核的研究空白候选及其证据依据。
- **进度与导出**：查看文献/文本块、问题、会话、笔记、比较、低文本页与待处理上传计数；导出 JSON 学习报告，包含文献版本摘要、问答与 EvidenceSpan、笔记、人工标签和 gap 候选，不包含本机绝对路径或全文。

## PDF 生命周期和边界

上传限定 PDF、最大 100 MB，先检查文件头并生成随机存储名，在 `.local/uploads/` 内保存。解析、题名/DOI候选、来源路径和索引块与现有管道共用。用户上传表只登记个人文件，删除路由先校验文件路径仍在应用管理目录；如果同 SHA 还存在授权目录来源，只移除上传副本路径并保留共享索引。如果它是唯一来源，则清理相应 FTS 块和版本记录，并递增索引修订号使潜在向量缓存失效。授权源文件没有删除按钮。

表单用会话 CSRF token；应用设置 100 MB 请求上限、关闭 debug 并只监听 loopback。没有登录系统，使用边界是运行用户的本机单用户环境；不要把监听地址改成 `0.0.0.0` 后当作共享服务。

## 使用与数据位置

```powershell
python -m papertrail web --db .local/papertrail.sqlite3 --sources configs/sources.example.yaml --selection configs/s1-pilot.jsonl --port 5000 --allow-local-dev-principal
```

本机访问 `http://127.0.0.1:5000`。上传 PDF、SQLite 数据库、向量制品、会话、笔记和评测轨迹均位于 `.local/`；源 PDF 只读。报告导出会保留 SHA、版本和 PDF 页码以供核验，同时剔除本机绝对路径和全文。

## 验证

`tests/test_s5_web.py` 覆盖授权清单载入、两篇 PDF 上传、引用问答、笔记隔离、跨论文证据收集、JSON 导出、上传删除和 CSRF。PT-4 后续回归还覆盖上传索引任务恢复、过期版本失效、Web/MCP ACL、脱敏 answer-eval 导出。最新定向 Web/answer-eval/MCP 集成测试 6 项通过；索引失败恢复及 ACL 生命周期相关测试 70 项通过。证据仅用合成 PDF，不调用模型。

## 已知限制

- 没有生成模型，Web 问答提供受校验的原文摘录，不生成自然语言综合结论。S4 的立场与空白候选都需要用户判断。
- 上传索引使用 SQLite 后台任务队列，失败可重试，进程恢复会重新排队；真实多进程 worker、崩溃注入和生产调度尚未验证。队列有任务级进度，但不提供实时页级解析流。
- 当前是单用户、单机工作台，不具备账户、远程协作或网络部署隔离。当地 Tesseract 未安装，OCR fallback 只会返回明确解析问题。
- 学习报告用于本地归档；个人笔记由用户自行撰写，未经论文页核验不会转成原文证据。

PT-4 展示回归确认 Web 显示证据片段、版本、PDF 页码和覆盖状态；answer-eval JSONL 只导出核验过的片段、SHA、页码及覆盖状态，不导出本机路径。collection owner 的 Web、直接读取和 MCP 资源权限由合成集成测试交叉核对。服务仍是本机单用户 demo，不代表生产多租户认证。

## 完成标记

S0–S5 的阶段归属、证据契约与用户体验汇总见[产品契约](../product-contract.md)。每个阶段单独使用中文提交信息；`.local/` 内容保持忽略，不进入 Git。
