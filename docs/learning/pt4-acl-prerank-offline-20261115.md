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

## BGE ACL 回归补充

原定向回归覆盖 BM25 SQL 与 TF-IDF/SVD 向量检索，但没有直接固定 BGE 后端的 ACL 顺序。本轮新增完全合成的 BGE bundle 测试：外部文档相似度更高，`bge_search` 仍先按 Principal 过滤，再评分和 top-k；无权限用户结果为空。测试 mock 编码器和索引加载，不调用 embedding 模型；不验证 BGE 质量或生产认证集成。

## direct-resource 与 MCP 权限边界

核查顺序：`_authorized_document` 的 SQL 同时约束 SHA、`original_pdf` 类型和 collection owner；无匹配时返回通用 not-found。只有授权后才读取路径并校验文件 SHA，再打开 PDF 页。MCP `get_evidence`、`resources/list`、`resources/read` 都要求服务端注入 `Principal`；请求内容里的 user id 不作为身份来源。`resources/list` 限定 owner 的原始 PDF，并按需校验文件 SHA；两个资源读取 URI 都回到授权文档查询。

新增合成集成回归，在两位 owner 间交叉调用直接页读取、文档 metadata、MCP evidence tool、资源列表和资源读取；确认只可读取各自 PDF，伪造 user id 参数无权扩权。测试不读取真实或私有 PDF。MCP stdio 服务本身仍是本地单用户进程，不提供调用者认证；多租户部署仍需可信身份注入层。

## 增量索引与任务恢复

现有索引回归已覆盖同一清单再次运行的 no-op、版本更新与删除、失败批次事务回滚，以及重试后发布新索引；旧版本和旧引用不可再读。新增队列恢复回归后发现上传任务缺陷：运行中的任务恢复排队后，第一次临时失败会先删除重试输入文件，导致后续尝试无法读取清单。现已仅在任务进入终态后清理输入文件。

新测试从 `running` 状态模拟进程恢复，注入第一次失败、第二次成功；验证两次均能读取输入、任务结束为 `succeeded`，终态才清理文件。只用合成配置和文件，不读 PDF、不调用模型。该回归验证单进程队列恢复路径，不构成多进程 worker 或崩溃注入的系统级保证。

新增合成 PDF 生命周期回归：物理 PDF 换版后，旧 SHA 的页校验、直接读取、搜索结果和无模型 QA 引文立即失效；reconcile 后旧 version/chunk 行清零。删除文件后，旧 QA 引文与访问同样拒绝，reconcile 后新版本 chunk 清零。重复跑同一清单不增加版本；恢复相同 PDF 字节并增量重建后，只保留一个版本，检索和 QA 返回的新引文再次通过页/文本校验。注意：物理源变更到 reconcile 之间，索引内部仍可能保留旧行；对外搜索按源 SHA 过滤，QA 与直接读取校验来源，reconcile 负责清除旧行。
