# PT4 来源版本与 ACL 审计（2026-11-12）

使用临时生成的合成 PDF 核验来源更新、删除、旧 citation 失效及 HTTP/MCP 权限一致性；没有读取私人 PDF。

## 结果

- 原 PDF 内容更新后，旧 SHA 从索引移除；旧页 citation 经 `read_evidence` 返回 `original paper not found`。重新登记新 SHA 后，新版本可读。
- PDF 删除后，reconcile 移除来源位置、版本和检索块；旧 SHA 不再出现在该 owner 的检索结果中，MCP 直接读取报错，HTTP 返回 404。
- 跨集合搜索由 `search_papers` 在查询时按 collection owner 过滤；直读由 `read_evidence` 使用同一 Principal 和 owner 联接校验。既有回归覆盖 HTTP、MCP 搜索、MCP 工具/资源直读和伪造请求体 user_id。
- 代码审计与合成测试未发现缺陷；新增测试把更新/删除后的失效行为固定下来。

定向验证：`tests/test_access_control.py`，**6 passed**。

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .tmp/pytest-pt4-acl tests/test_access_control.py
```

不代表生产身份认证、多租户部署或真实文献质量已验证。跨集合安全依赖部署层正确注入 Principal；本地测试直接构造 Principal。
