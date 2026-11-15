# PT-4 上传与索引任务 owner 隔离（2026-11-15）

## 门槛判断与缺口证据

PT-3 真实回答质量仍依赖 PT-1 双人 gold 和单独批准的模型评测；PT-1 继续暂停。PT-4 生产 Principal provider 也仍需部署方提供，但本地多 Principal 路径还能做确定性加固，因此选 PT-4 上传/索引状态隔离。

静态核对发现 `user_uploads` 与 `index_jobs` 都没有 owner 字段。Web 首页列出所有上传；删除只按 upload ID 查询；索引任务状态也只按 job ID 查询。三个路径都未把可信 `g.principal.user_id` 传入存储查询。现有 API 无法表达按 owner 读取，新增回归最初因 `register_upload(..., owner_id=...)` 和 `list_uploads(database, owner_id)` 不支持 owner 参数而失败。

## 修复

- `user_uploads`、`index_jobs` 新增 `owner_id` 与按 owner/时间索引。旧 schema 迁移把既有单用户记录归为 `local-dev`，保持原本本机单用户行为。
- Web 上传、首页列表、删除和 `/jobs/<id>` 状态读取均使用当前可信 Principal。跨 owner 查询统一表现为不存在；不能列出或删除他人上传，也不能读其索引任务错误和进度。
- `register_upload`、`enqueue_index`、`list_uploads`、`remove_upload`、`get_job` 保留 `local-dev` 默认值，兼容单用户调用。生产认证 provider 仍由部署方提供，本地测试不冒充生产认证集成。

## 回归

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_s5_web.py tests/test_access_control.py tests/test_jobs.py tests/test_pt4_acl_retrieval_regressions.py
```

结果：**41 passed**。新增回归覆盖两位 Principal 的上传列表/删除隔离、HTTP 上传与任务状态隔离、旧上传/任务 schema 迁移。输入只来自临时 SQLite、合成 PDF 和合成身份；未读私人 PDF、修改冻结 gold 或调用模型。`.tmp/` 与 `.codex-test-tmp/` 未清理。

本轮只完成上传记录与索引状态的 owner 隔离，不代表生产认证或完整多租户安全验收完成。PT-1 继续暂停。
