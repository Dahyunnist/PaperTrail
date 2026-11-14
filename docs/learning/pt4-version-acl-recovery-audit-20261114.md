# PT-4 版本失效、恢复与 ACL 审计（2026-11-14）

## 审计结论

既有实现和合成回归已覆盖来源替换后旧 SHA 不再被索引/检索、旧 Web/MCP evidence URI 失效、新版本按集合 owner 继承 ACL、未授权 Principal 无法搜索或读取；来源删除及 selection 移除后也会清除可检索记录并使旧引用失败。SQLite 对账解析失败与写入失败均有回滚后重试测试。

发现一处测试覆盖缺口：删除并从 selection 移除后，已有测试确认索引为空，但未验证重新放回同一合成源版本并重新加入 selection 后能否恢复索引。现已在 `test_reconcile_updates_changed_paths_and_removes_deleted_sources` 增补恢复断言：删后旧 SHA 不可检查、检索为空；恢复原合成 PDF 字节并对账后，版本重新建立且可按内容检索。未修改生产逻辑。

PT-4 定向测试 **5 项通过**：来源替换/删除/恢复、解析与写入失败回滚、Web/MCP 旧引用失效及 ACL 隔离。测试仅生成临时合成 PDF，不创建用户资料或读取私人文档。

## 边界

这些测试证明索引版本和本地集合 ACL 在固定合成路径下的行为，不证明生产 Principal provider/SSO 的身份真实性、共享反向代理部署安全或生产多租户验收。PT-1 人工 gold 仍为 0/40；真实文献与生产身份验收继续等待相应人工/部署输入。

## MCP/Web ACL 复核（2026-11-14）

再次运行 `tests/test_access_control.py` 与 `tests/test_s1.py`：**27 passed**。负例确认：删除/替换源后旧 SHA 不再出现在检索结果，HTTP 证据和 MCP `get_evidence`/`resources/read` 均拒绝旧引用；`resources/list` 只列出 owner 当前可读且源文件 SHA 匹配的 PDF。跨 owner 的 Web 搜索、MCP `search_papers`、MCP 资源列表/直读、HTTP evidence 均一致拒绝；新版本只继承预期集合 ACL。未发现需修复的实现缺口，因此本次不改生产代码，只补恢复索引测试和本审计记录。

后续 Windows 临时目录复验发现 MCP `_readonly` 仍以未编码路径拼 SQLite URI，路径含 `#!` 时触发 `unable to open database file`，导致资源 ACL 负例无法运行。已改用 `Path.as_uri()` 编码；`tests/test_access_control.py` 与 `tests/test_s1.py` 复跑 **27 passed**。这修复测试与实际部署中的特殊 Windows 路径兼容，不改变 ACL 判定。
