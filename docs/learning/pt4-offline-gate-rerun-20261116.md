# PT4 离线门禁复核（2026-11-16）

## 结论

PT4 本地应用层 ACL、版本失效/重建及 Web/MCP 共享授权门禁已有实现和负例覆盖。本轮仅复核，没有发现需要新增代码或回归的缺口。

## 复核与结果

审查 `papertrail/access.py`、`papertrail/web.py`、`papertrail/mcp_server.py`、`papertrail/workspace.py`、`papertrail/jobs.py` 与索引 reconcile 路径，并复跑：

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q tests/test_access_control.py tests/test_pt4_acl_retrieval_regressions.py tests/test_jobs.py tests/test_s5_web.py tests/test_pt2_hybrid_version_lifecycle.py tests/test_pt3_citation_failure_paths.py tests/test_s1.py
```

结果：**56 passed**。测试使用临时 SQLite、合成 PDF、合成 Principal 和故障注入。覆盖：

- 缺失 Principal 失败关闭；HTTP header/body 与 MCP 参数不能伪造用户身份。
- Web/MCP 检索、direct evidence、resource、导出、上传和 job 状态按 owner 隔离。
- ACL 先于 BM25、向量候选排序及 top-k 限额。
- 来源换版或删除后旧搜索结果和引用失效；reconcile 清理旧版本并保留 collection owner。
- reconcile 写入失败原子回滚，重试后发布完整新索引。
- citation 绑定来源 SHA、物理页和原文 span。

没有读私人 PDF 或 gold，没有调用模型，没有清理 `.tmp/`、`.codex-test-tmp/`，没有推送。

## 未完成门槛

生产认证与跨进程边界未验证。需要部署方提供可信 Principal 注入契约、目标 Web 身份中间件和实际 MCP transport，再验证匿名/伪造身份拒绝与跨用户拒绝。现有 MCP CLI 的本地开发身份选项不等于 transport 调用者认证。本轮离线结果不证明生产多租户认证。
