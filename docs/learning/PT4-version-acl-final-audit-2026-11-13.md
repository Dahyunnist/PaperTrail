# PT-4 版本、ACL 与导出验收（2026-11-13）

范围：仅使用测试生成的合成 PDF/SQLite。未读取私人论文或提交用户数据。PT-1 双人 gold 仍为 0/40，等待用户标注。

| 检查项 | 实现/证据 | 回归结果 | 边界 |
|---|---|---|---|
| 源 PDF 更新后旧引用失效 | `access.read_evidence` 校验当前路径内容 SHA；`index_selection(reconcile=True)` 清理旧版本 | `tests/test_access_control.py::test_updated_and_deleted_sources_invalidate_old_citations_across_http_and_mcp` 通过 | 更新后需 reconcile 才发布新版本 |
| 删除、增量重建与恢复 | reconcile 删除无来源版本；新 SHA 重新索引；整批预解析/写入原子回滚 | `tests/test_s1.py::test_reconcile_updates_changed_paths_and_removes_deleted_sources`、`test_reconcile_parse_failure_keeps_published_index_then_retry_succeeds`、`test_reconcile_write_failure_rolls_back_entire_batch_then_retry_succeeds` 通过 | 测试使用临时合成 PDF |
| 集合 ACL 搜索 | HTTP 与 MCP search 使用 Principal 过滤 | `tests/test_access_control.py::test_http_and_mcp_share_acl_and_http_ignores_body_user_id` 通过 | 有效身份注入依赖部署契约 |
| Direct resource ACL | MCP document/evidence resources 与 tool read 校验同一 collection owner | `tests/test_access_control.py::test_mcp_direct_resources_enforce_collection_acl` 通过 | 仅合成库 |
| HTTP direct evidence | 跨用户请求返回 404；旧/删除来源请求拒绝 | 更新删除端到端测试通过 | 不泄露对象是否存在 |
| citation 页码/原文定位 | 引文引用绑定 SHA、物理页与逐字 span；PT-3 citation 测试覆盖错误来源/页证据 | `tests/test_pt3_citation_failure_paths.py` 纳入全套测试 | 不代表真实 gold 完整性 |
| JSONL 导出 | PT1 CSV importer 产出本地 gold JSONL，校验 SHA 与 PDF quote/span；它不是按用户 ACL 的服务端导出接口 | `tests/test_pt1_human_csv_import.py` 纳入前轮 25 项回归 | 输出必须留本机 `.local`；不能将公共格式误当多租户导出 |

本轮命令 `python -m pytest tests/test_s1.py tests/test_access_control.py tests/test_mcp_server.py tests/test_s5_web.py tests/test_s4.py tests/test_reward.py -q`：27 passed。全套 pytest：189 passed、1 failed。唯一失败为 `tests/test_local_llm.py::test_local_chat_client_uses_loopback_ollama_json_api`，宿主禁止测试服务器 bind `127.0.0.1`（WinError 10013）；保留原集成测试及断言，另有 `test_ollama_json_contract_with_injected_transport` 验证同一 HTTP 请求契约，不开 socket、不调用模型。

没有新增未经核验的论文数据。没有运行模型。`.tmp/` 未暂存。PT-4 多租户仍需可信身份契约；当前有效 Principal 不代表跨用户工作区隔离。
