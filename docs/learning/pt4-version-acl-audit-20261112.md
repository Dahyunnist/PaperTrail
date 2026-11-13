# PT4 来源版本与 ACL 审计（2026-11-12）

使用临时生成的合成 PDF 核验来源更新、删除、旧 citation 失效及 HTTP/MCP 权限一致性；没有读取私人 PDF。

## 结果

- 原 PDF 内容更新后，即使索引尚未 reconcile，文档元数据和页资源都因当前文件 SHA 不匹配而拒绝；reconcile 后旧 SHA 从索引移除。重新登记新 SHA 后，新版本可读。
- PDF 删除后，reconcile 移除来源位置、版本和检索块；旧 SHA 不再出现在该 owner 的检索结果中，MCP 工具直读、`papertrail://documents/{sha}` 元数据资源和 `papertrail://evidence/{sha}/{page}` 页资源均拒绝，HTTP 返回 404。
- 跨集合搜索由 `search_papers` 在查询时按 collection owner 过滤；直读由 `read_evidence` 使用同一 Principal 和 owner 联接校验。既有回归覆盖 HTTP、MCP 搜索、MCP 工具/资源直读和伪造请求体 user_id。
- 新增资源 URI 负例：跨 owner 的元数据和页资源读取均拒绝；来源更新或删除后、索引同步前，旧 SHA 的两类资源也失效；reconcile 后旧记录继续不可读。

定向验证：`tests/test_access_control.py`、`tests/test_mcp_server.py`、`tests/test_s5_web.py`，**12 passed**。

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .tmp/pytest-pt4-acl-regression tests/test_access_control.py tests/test_mcp_server.py tests/test_s5_web.py
```

本机 MCP stdio 固定使用 `local-dev`，没有调用方身份认证；当前明确按单用户本机服务运行，不宣称多租户支持。嵌入式调用的集合隔离测试直接构造不同 Principal；生产身份认证及可信 Principal 注入仍待部署集成。真实文献质量未在此验证。

## Reconcile 批次失败原子性（2026-11-13）

index_selection(reconcile=True) 现在先解析完整批次，再变更已发布索引。第二篇文档解析注入失败时，数据库字节保持不变，旧版本仍可用；移除故障后重试，两篇新版本一次发布，旧 SHA 不再可读。	ests/test_s1.py::test_reconcile_parse_failure_keeps_published_index_then_retry_succeeds 与 	ests/test_access_control.py::test_updated_and_deleted_sources_invalidate_old_citations_across_http_and_mcp：2 passed。

