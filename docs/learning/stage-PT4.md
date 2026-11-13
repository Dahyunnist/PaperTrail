# PT4：版本对账、索引失效与权限边界

日期：2026-10-23

## 来源版本与增量恢复

`paper_versions.version_id` 仍由源 PDF 的 SHA-256 确定，解析版本另存于 `parser_version`。配置目录的“索引已选来源”现在把所选清单视为这些配置 root 的完整快照：清单遗漏或文件删除会清除旧位置；同一路径哈希变化会解绑旧版本并索引新版本。重复运行不改索引修订号；新增、替换、删除会递增修订号，供向量索引识别过期。源文件从不由对账操作删除。

清单先整体解析和校验，再做对账。完整快照对账把旧位置解绑、论文版本/分块/FTS 写入和索引修订号放在同一个 SQLite 事务中。任一文档写入失败，整批回滚；旧索引继续可查，同一清单可安全重试。进度回调会另开连接写任务表，因此完整快照提交前先缓存进度，提交后再回调，避免与索引事务争用 SQLite 写锁。普通增量索引仍按文档独立提交。后台任务仍按原队列恢复。个人上传采用独立单文件任务，不把它误当成上传目录的完整快照。上传删除只删应用管理目录内文件；共享哈希版本在仍有其他来源位置时保留。

## 测试环境复查

仓库原先没有 `pyproject.toml`、依赖锁或 Python 版本声明；`requirements-dev.txt` 只有宽范围直接依赖。采用本机提供的 Windows x64 CPython 3.12.14，建立 `.venv`，并添加 `.python-version` 与精确版本快照 `requirements-dev.lock`。`pip check` 通过。新环境复现命令见 README。

PT4 临时数据库用例覆盖同清单幂等、源哈希变化、删除失效和修订号。首次定向运行发现 MCP 在请求证据时使用旧 `fitz` 别名，PyMuPDF 新版向 stdout 写弃用警告，破坏 JSON-RPC；改用 `pymupdf` 后通过。

新增第二篇文档写库故障注入：先建立两篇旧版本，再替换来源；在第二篇写入时抛错，断言 SQLite 表、FTS 和修订元数据均回到原快照，旧文档仍可检索且新版本未部分发布。恢复写入后重试，同批两篇新版本完整可检索，旧版本失效。定向命令：`python -m pytest tests/test_s1.py::test_reconcile_write_failure_rolls_back_entire_batch_then_retry_succeeds tests/test_s1.py::test_reconcile_parse_failure_keeps_published_index_then_retry_succeeds tests/test_s1.py::test_reconcile_updates_changed_paths_and_removes_deleted_sources -q`；结果 `3 passed`。

Web 后台进度回调另开 SQLite 连接，若在整批事务内更新任务行会争用写锁。完整快照现在延后发布进度；`tests/test_s5_web.py::test_web_can_index_explicit_authorized_selection` 通过。全套可运行测试：`180 passed, 1 deselected`；排除项是需要 loopback socket 的本地 Ollama 测试，当前受限环境不允许绑定 socket。

完整测试：`52 passed in 26.04s`。已运行 `tests/test_s1.py`、`tests/test_s3.py`、`tests/test_s5_web.py`、`tests/test_mcp_server.py` 定向回归，并运行全量 pytest。没有调用模型。

## Web 与权限边界

文献列表显示内容版本 ID 与哈希。已保存回答显示 claim、原文引句、物理 PDF 页、版本 ID；保存覆盖缺项，可区分有缺项与未记录缺项。

应用与 MCP 服务均使用一个 `PAPERTRAIL_DB`。本地默认 Principal 固定为 `local-dev`。HTTP 认证中间件可通过服务端 WSGI environ 注入 `Principal`；MCP 嵌入调用可显式传入 `Principal`。请求参数和请求体不提供 `user_id` 入口。

本轮加入 `collections(owner_id)`，论文版本关联集合。共享 `access.py` 的检索在 SQL 候选过滤前按 Principal 的 owner 限制；向量和 BGE 检索先筛出授权版本，再计算候选分数。页证据先校验集合所有权，再核验 PDF 当前 SHA 与页码。HTTP `/api/search`、`/api/evidence/<sha256>/<page>`、问答及 MCP `search_papers`、`get_evidence` 共用此授权边界；MCP 资源列表和读取也按 owner 隔离。

测试覆盖 A/B 两个 Principal 的检索隔离、跨集合直接 SHA 读取拒绝、HTTP 与 MCP 共用授权、HTTP 不采信请求体伪造 `user_id`，以及默认 `local-dev` 对既有单用户库的访问。此为应用层授权测试，不代表生产身份认证或完整多租户安全验收。生产部署必须由可信认证中间件注入 Principal；当前不做登录界面。

## API 与隐私

PT4 ACL 定向回归：42 passed。全仓回归：86 passed；单独运行被排除的 `test_local_chat_client_uses_loopback_ollama_json_api`：1 passed。普通运行环境拒绝该测试的 loopback 连接，获准本机回环测试后通过。测试还覆盖旧数据库迁移和重建索引后保留集合 owner。PT4 不调用模型。未读取或提交本机论文路径、私有 PDF、题目、摘录或忽略目录内容。
