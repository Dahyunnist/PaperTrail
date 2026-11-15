# PT-4 检索前 ACL 与索引失效离线复验（2026-11-15）

## 复验范围

仅用测试即时生成的合成 PDF 与两到三个合成 workspace/collection。未读取私人 PDF、PT-1 gold、任何 holdout 或真实用户数据；未调用模型；未改 gold。

代码路径审计：

- FTS 检索在 SQL 中通过 `collections.owner_id` 过滤，然后执行 BM25 排序和候选限额。
- 纯向量检索先取授权 `version_id` 集，再计算相似度和 top-k。
- hybrid 路径将同一 `principal_id` 传给 BM25 与向量两端；重排只接收已授权候选。
- Web `/api/search` 与 JSONL 导出使用服务端注入的 `Principal`；请求头、请求体中的用户标识不覆盖该身份。
- reconcile 对换版先脱离旧路径/版本，再写入新版本；沿用原 collection ACL；提交时增加索引 revision。物理删除也会清理旧版本、chunk 和 FTS 行。

## 新增负例与结果

新增三个离线回归：

1. 五份高分外部文档与一份低分本 workspace 文档竞争 top-1。BM25 与 Web API 仍返回有权限的文档；外部文档的 BM25 分数确实更高，证明 ACL 在排序/限额前生效。无权限用户得到空结果。
2. 向量检索使用受控合成分数：外部文档得分高于有权文档。检索仍只返回有权文档；无权限用户返回空集。此用例验证授权候选先于相似度排序和 top-k。
3. `reconcile` 换版后旧 SHA/version 不再授权或可读，新版本保留原 owner；删除后授权版本为空、检索为空、旧/新证据均不可读。

定向命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_pt4_acl_retrieval_regressions.py tests/test_access_control.py tests/test_s5_web.py tests/test_pt2_hybrid_version_lifecycle.py tests/test_s1.py::test_reconcile_updates_changed_paths_and_removes_deleted_sources
```

结果：**31 passed**。机器摘要见 `evals/pt4-acl-prerank-report-20261115.json`。

## 覆盖边界

已验证本地 SQLite、合成 Principal、Web 测试客户端、MCP 既有 ACL 回归、BM25 SQL 限额、受控向量排序及本地 reconcile 失效语义。没有生产身份提供方、部署网关、跨进程缓存一致性或真实多租户存储的集成证据；受控向量分数证明过滤顺序，不验证真实向量模型质量。不得据此宣称生产认证或多租户安全验收完成。
