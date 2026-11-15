# PT-4 离线复现与演示（2026-11-15）

## 一键演示

在已安装项目开发依赖的 Windows PowerShell 中运行：

```powershell
py -3.12 scripts/demo_pt4_offline.py
```

脚本在系统临时目录创建一份合成 PDF 和 SQLite 索引，演示 Web 引文页码、两种 JSONL 导出、HTTP/MCP ACL、来源替换前的过期拒绝，以及 reconcile 后原 owner 权限继承。演示结束会自动删除临时目录，不碰 `.local/`、`.tmp/`、`.codex-test-tmp/` 或用户文档。

成功时 JSON 输出应包含以下 `true` 结果：

- `citation_quote_and_page_visible_in_web`
- `search_export_omits_source_text`
- `answer_eval_export_matches_sha_and_page`
- `mcp_direct_read_allowed_for_owner`
- `cross_owner_search_denied_in_http_and_mcp`
- `changed_source_hidden_before_reconcile`
- `changed_source_direct_read_rejected`
- `owner_acl_preserved_after_reconcile`
- `old_version_removed_after_reconcile`

输出同时标记 `synthetic_only: true`、`models_called: 0`、`private_files_read: 0`。

## 一键回归

```powershell
py -3.12 -m pytest -q -p no:cacheprovider `
  tests/test_access_control.py `
  tests/test_s1.py `
  tests/test_mcp_server.py `
  tests/test_s5_web.py `
  tests/test_pt4_acl_retrieval_regressions.py `
  tests/test_pt3_citation_failure_paths.py
```

此组覆盖 HTTP/MCP 共用 ACL、过期来源过滤、增量更新/删除、Web 引文与 JSONL 位置校验，以及替换文件期间引用页快照一致性。测试使用合成 fixture，不会启动真实模型或读取私有 PDF。

## 结果边界

这是 PT-4 工程行为演示，不是 PT-1 人工 gold，也不代表 PT-1、PT-2 或 PT-3 验收完成。PT-1 继续暂停；PT-3 回答正确率不由这些 ACL/导出测试推断。
