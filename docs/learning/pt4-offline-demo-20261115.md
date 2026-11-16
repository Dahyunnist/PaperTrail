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

## 离线切片复核（2026-11-16）

代码与现有合成测试已覆盖 collection/document ACL、过期版本搜索/直接读取拒绝、删除后失效、reconcile 后旧版本清理和 owner 继承，以及 Web evidence/JSONL 与 MCP resource/tool 读取路径。本轮未发现可补的 PT-4 边界，因此不增加功能。

复核定向回归：**9 passed**。包含 `test_collection_acl_filters_search_and_direct_evidence_reads`、HTTP/MCP 共享 ACL、MCP direct resources、跨入口换版/删除失效、reconcile ACL 可见性、增量重建恢复及 source reconcile 删除。数据由测试即时生成，未读 gold、私人 PDF 或既存临时目录；未调用模型。

一键演示入口仍为 `scripts/demo_pt4_offline.py`，复现命令见上文。演示代码使用 `TemporaryDirectory` 和合成 PDF/SQLite；未在本轮运行演示，避免触碰临时目录。生产身份 provider 与实际部署身份验证仍未覆盖。

## PT-4 七项回归与路线验收映射（2026-11-16）

单独复跑 `tests/test_pt4_acl_retrieval_regressions.py`：**7 passed**。七项分别覆盖：

1. `test_acl_filters_before_fts_limit_and_web_search`：无权高分来源不能挤掉授权 top-k；Web 搜索同样隔离。
2. `test_vector_candidates_are_filtered_before_scoring_and_top_k`：向量候选在评分和 top-k 前按 Principal 过滤。
3. `test_bge_candidates_are_filtered_before_scoring_and_top_k`：BGE 候选同样先做 ACL 过滤。
4. `test_direct_reads_and_mcp_tools_resources_share_collection_acl`：跨 collection 页证据、metadata、MCP tool、resource list/read 均拒绝；授权来源可读。
5. `test_reconcile_update_and_delete_clean_versions_and_acl_visibility`：换版继承 collection owner，旧版/删除版不可检索或读取。
6. `test_replaced_and_deleted_citations_expire_and_incremental_rebuild_recovers`：旧 citation 随换版/删除失效；重建后新 citation 可验证。
7. `test_web_export_direct_read_and_mcp_share_acl_and_render_verified_evidence`：Web 页/JSONL 的 SHA、页码、片段与 MCP direct resource 一致，跨 owner 拒绝。

以上仅证明本机 synthetic fixture 下的应用 ACL 与索引生命周期，不证明生产身份提供方或 MCP transport 认证。测试未读取私人 PDF/gold，未调用模型；没有发现需补的代码回归。
