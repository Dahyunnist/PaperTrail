# PT-4 多入口 ACL 离线核对（2026-11-15）

## 复验

全用测试临时 SQLite、即时合成 PDF 和两位 synthetic Principal。检索前过滤、Web、direct evidence、MCP tool/resource、换版/删除、上传 owner 与 job 状态组共 **43 passed**：ACL 回归文件 7 项，另有 access-control、Web、版本生命周期、reconcile 和 jobs 组 36 项。

负例确认无权文档即使排序分更高，也不会挤掉 top-k 内授权文档；BM25、向量和 BGE 均先按 Principal 限权。HTTP 与 MCP 直接读、资源列表/读取、导出、上传列表/删除及 job 状态均覆盖跨 owner 拒绝或隔离。SHA 换版和删除后，旧证据失效，新版本保留 collection owner。

本组只证明本地 SQLite 与测试 Principal 下的应用 ACL 行为；不测真实身份 provider、部署网关、MCP stdio 调用者认证或多进程共享存储，不能外推为生产多租户安全。

## 下一具体缺口

部署方尚未提供并联测可信 Principal provider。下一步应在目标认证中间件和实际 MCP transport 上验证匿名拒绝、身份伪造拒绝、跨用户读取拒绝，再做部署级审计。无需重复扩展本地合成 ACL 用例。本轮未读私人 PDF、未碰真实 gold、未调用模型。
