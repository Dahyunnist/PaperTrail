# PT-4 Principal、审阅记录与导出边界

Web 本机单用户模式仍默认使用 `local-dev`。配置 `REQUIRE_PRINCIPAL=True` 后，缺失 Principal 或身份提供器返回无效值时请求以 401 失败；请求体的 `user_id` 不能充当身份。生产认证仍由可信身份提供器注入，仓库没有伪造登录或 token 验证。

集合 ACL 继续隔离论文检索、页证据和 MCP 资源。工作区笔记、QA 历史、比较、上传记录及学习报告仍共用一个 SQLite 数据库，尚无 owner 列或按 Principal 分库。因此当前产品边界是单用户本机，不是多租户；即使 Principal 有效，也不能把同一数据库部署给互不信任用户。导出报告是整个本机工作区报告，不提供按用户过滤。

比较证据标注现在持久化 `reviewer_id` 与 `labeled_at`；QA 轨迹评分持久化 `reviewer_id` 与 `rated_at`。Web 标注从可信 Principal 传入审阅者 ID；CLI 与旧调用默认 `local-dev`。启用 `PAPERTRAIL_TRACE_JSONL` 时，两类操作另发隐私受限 `human.reviewed` 事件。SQLite 审阅字段是持久审计记录；JSONL 追踪仍是可选记录。

学习报告导出会去除证据对象中的本机文件路径。它仍包含本机单用户的笔记、问题、回答和比较内容；不要把它当成用户隔离的多租户导出。

验证：`tests/test_s5_web.py`、`tests/test_s4.py`、`tests/test_reward.py`、`tests/test_access_control.py`、`tests/test_mcp_server.py` 共 **17 passed**。合成数据库/PDF 覆盖匿名失败关闭、Web 审阅者身份传递、审阅者/时间持久化、路径导出隔离及集合 ACL。没有读取私人 PDF，也没有调用模型。
