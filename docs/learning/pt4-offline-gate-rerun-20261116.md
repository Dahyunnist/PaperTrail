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

## MCP stdio JSON-RPC 集成补充

新增真实子进程 stdio 测试 `tests/test_mcp_stdio_auth_boundary.py`，使用合成双用户与两份合成 PDF。匿名进程和 JSON-RPC 中伪造 `user_id` 对 search、resource list/read 均失败关闭；由受信启动代码注入 `Principal` 的 owner-a、owner-b 进程分别可读本方证据，跨 owner 直读被拒。它验证真实换行 JSON-RPC 输入/输出与 ACL 路径，不伪造 MCP 身份认证协议。

命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q tests/test_mcp_stdio_auth_boundary.py tests/test_mcp_server.py tests/test_access_control.py
```

结果：**22 passed**。

## 未完成门槛

MCP stdio 本身没有调用者认证字段。测试中的授权身份由服务端启动层可信注入；匿名启动保持 `principal=None` 并拒绝受保护操作。生产认证仍需部署方提供注入契约和目标认证层联测。跨进程/共享存储隔离也未测试；本地结果不证明生产多租户认证。

## 问答评审页面与导出补充

界面复查发现复杂问题拆解仅存在于当次 `ask()` 结果，未写入 `qa_turns`；历史页面和 answer-eval JSONL 因而缺少拆解上下文。新增兼容迁移字段 `subquestions_json`，保存实际多子问题拆解；单问题和旧记录默认空列表。Web 对话展示拆解条目，并提供“下载人工评审 JSONL”链接。评审导出增加 `subquestions`；原有 `human_score`、`reviewer`、`review_notes` 空字段供离线人工填写。覆盖状态、claim、原文摘录、PDF 页码、版本 SHA 展示逻辑保持现有校验。

定向回归 `tests/test_s5_web.py tests/test_access_control.py tests/test_s3.py`：**64 passed**。覆盖页面拆解/导出链接、历史持久化、旧 schema 迁移、JSONL 子问题和评分字段、来源 ACL 与过期引文拒绝。用例使用临时合成 PDF/DB，并 mock 问题拆解/审查；没有调用模型或读取真实 gold/私人 PDF。

人工答案评分通过下载 JSONL 后填 `human_score`、`reviewer`、`review_notes`。本页没有直接提交答案评分的表单；若要求在线录入评分，仍需单独实现有 owner 校验的保存流程。

## 在线评分补充

完成上述缺口：新增 Web QA 评分表单与 owner-scoped 保存路由。评审人始终取自 `g.principal.user_id`，不接受客户端指定；评分类型复用 `reward.RATING_BASE` 的五类，备注由现有 `rate_trajectory` 限长并保存。提交前按 conversation owner 校验 turn，跨 owner 404。历史页显示已保存评分；answer-eval JSONL 返回该评分、reviewer 和备注。

定向运行 `tests/test_s5_web.py tests/test_access_control.py tests/test_reward.py`：**33 passed**。含跨 owner 拒绝和评分 JSONL 往返。没有真实人工评分样本；真实问答质量仍待 PT1 双标数据，PT1 保持暂停。

## 对话列表隔离补充

代码审查发现首页“最近对话”SQL 未按 `owner_id` 限制，会显示其他 Principal 的标题与 conversation ID；query-string 直接打开外部 conversation 则未捕获 `conversation_history` 的 not-found 错误。现按可信 Principal 过滤列表，直接访问外部 conversation 返回 404。

定向测试 `tests/test_access_control.py tests/test_s5_web.py`：**33 passed**。新负例先在旧实现下失败，明确重现标题泄露；修复后验证本人条目可见、他人条目隐藏、直接跨 owner 访问返回 404。仅临时合成 DB/QA 记录。

本次只修复问答对话列表/查看边界。生产 IdP/MCP transport 仍待部署方；文献库列表与全局仪表盘计数目前仍按共享索引呈现，后续需明确共享库产品边界或补 owner 过滤，不在本次扩展。

## MCP 资源与版本生命周期 stdio 复核

起始 `HEAD` 与 `origin/master` 均为 `f97886845e231abd6f8c61a2b2e39f10ee388418`，无 ahead/behind。复核发现 ACL/direct-resource 与版本失效已有单元/HTTP/内存 handle 回归，但真实 stdio 测试尚未串起授权资源读取、跨 owner 资源拒绝及换版前后读取。

扩展 `tests/test_mcp_stdio_auth_boundary.py`：owner-a/owner-b 子进程分别只能列出和读取本方资源；换版未 reconcile 前资源列表隐藏旧 SHA、旧 evidence URI 读取失败；reconcile 后新 URI 可读、旧 URI 仍失败。该扩展未发现实现缺陷，不改运行时代码。

定向命令 `tests/test_mcp_stdio_auth_boundary.py tests/test_mcp_server.py tests/test_access_control.py tests/test_pt4_acl_retrieval_regressions.py tests/test_pt3_citation_failure_paths.py tests/test_pt2_hybrid_version_lifecycle.py`：**36 passed**。仅临时合成 PDF/SQLite 与可信测试 Principal；未读私人 PDF/gold，未调用模型。

剩余边界：stdio 调用者认证依赖服务端外部 Principal 注入；生产身份集成及跨进程共享存储仍待部署环境。PT1 双人标注继续暂停。

## PT4 验收项证据矩阵（2026-11-16）

首页文献清单测试先在旧实现下失败：owner A 页面包含 owner B 的 `beta.pdf` 和 SHA。`library_documents` 现在通过 `paper_versions.collection_id → collections.owner_id` 过滤；Web 按可信 Principal 调用。兼容默认仍为 `local-dev`。

| 计划门槛 | 当前证据 | 结果 |
|---|---|---|
| 源替换/删除、索引修订与增量恢复 | `tests/test_s1.py::test_reconcile_updates_changed_paths_and_removes_deleted_sources`；`tests/test_pt2_hybrid_version_lifecycle.py::test_hybrid_retrieval_tracks_synthetic_version_update_and_delete` | 通过 |
| reconcile 解析/写入事务失败后可重试 | `tests/test_s1.py::test_reconcile_parse_failure_keeps_published_index_then_retry_succeeds`；`test_reconcile_write_failure_rolls_back_entire_batch_then_retry_succeeds` | 通过 |
| ACL 在 BM25、向量、BGE 排序和 top-k 前生效 | `tests/test_pt4_acl_retrieval_regressions.py::test_acl_filters_before_fts_limit_and_web_search`；`test_vector_candidates_are_filtered_before_scoring_and_top_k`；`test_bge_candidates_are_filtered_before_scoring_and_top_k` | 通过 |
| HTTP/MCP direct evidence、resources list/read 双用户隔离 | `tests/test_pt4_acl_retrieval_regressions.py::test_direct_reads_and_mcp_tools_resources_share_collection_acl`；`tests/test_mcp_stdio_auth_boundary.py::test_stdio_transport_fails_closed_without_trusted_principal_and_scopes_injected_users` | 通过 |
| 源变更后旧 SHA/引用失效，新版 ACL 保留 | `tests/test_pt4_acl_retrieval_regressions.py::test_replaced_and_deleted_citations_expire_and_incremental_rebuild_recovers`；`tests/test_access_control.py::test_replaced_version_hides_stale_search_and_preserves_acl_across_web_mcp_resources` | 通过 |
| 引文绑定 SHA、物理页、chunk 原文；过期来源拒绝 | `tests/test_pt3_citation_failure_paths.py`；`tests/test_access_control.py::test_read_evidence_uses_same_bytes_for_sha_check_and_page_lookup`；answer-eval export expired-source regression | 通过 |
| 上传、索引 job、conversation 和答案评分 owner 隔离 | `tests/test_s5_web.py::test_personal_uploads_are_scoped_to_trusted_principal`；`tests/test_jobs.py::test_index_job_status_is_scoped_to_owner`；`tests/test_access_control.py::test_qa_conversation_owner_is_bound_and_checked_on_reuse_and_history`、`test_web_answer_review_is_owner_scoped_and_included_in_jsonl` | 通过 |
| Web 文献元数据不跨 owner 泄漏 | `tests/test_access_control.py::test_web_library_document_metadata_is_scoped_to_collection_owner` | 通过；旧实现曾失败 |

全量 PT4 离线组复现命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q tests/test_access_control.py tests/test_pt4_acl_retrieval_regressions.py tests/test_mcp_stdio_auth_boundary.py tests/test_mcp_server.py tests/test_jobs.py tests/test_s5_web.py tests/test_pt2_hybrid_version_lifecycle.py tests/test_pt3_citation_failure_paths.py tests/test_s1.py
```

结果：**61 passed**。仅测试生成的 PDF、SQLite 和身份；无私人 PDF/gold、模型或外部服务。

## 尚需外部决策/环境

- 生产 Web 身份中间件、实际 MCP host 的可信 Principal 注入、跨进程/共享存储：需部署方环境和认证契约，当前不可离线验证。
- PT1 双标 gold 与 PT2/PT3 真实质量指标：PT1 仍暂停；需两位人工标注者独立核验可回答性、最小证据 span、claim 支持/冲突，再仲裁分歧。未生成 gold。
- `dashboard_stats`、个人笔记和比较记录仍是共享工作区数据；现有 PT4 验收清单未定义它们是否按 Principal 隔离。若要多租户隔离，先定产品边界再扩展 owner schema。

起始 `HEAD` 与 `origin/master` 同为 `872e9c7d4be6abe8bba2e29af57e039fcf5efd3e`；本次变更提交后不推送，保留供主控快进处理。
