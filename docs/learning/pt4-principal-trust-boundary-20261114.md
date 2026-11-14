# PT-4 Principal 注入信任边界（2026-11-14）

## 问题与收紧

此前 Web 在没有服务端身份注入时回退到 `local-dev`；MCP handler/stdio 入口也默认使用 `local-dev`。因此 collection ACL 虽然在搜索、直接证据和资源读取中执行，但缺少身份认证的调用仍获得默认 owner 身份。

现在 Web 只有 `PRINCIPAL_PROVIDER` 返回有效 `Principal` 才接受认证请求。缺失、异常类型或 provider 返回 `None` 均失败关闭为 401。身份不再从 Flask request environ、header、query 或 body 推导。`--allow-local-dev-principal` 是明确的本机演示开关，只接受 loopback 请求且所有请求共享固定 `local-dev`；不支持跨用户身份隔离。

MCP 的 `tools/call`、`resources/list`、`resources/read` 以及直接证据函数默认要求调用方通过可信服务端参数注入 `Principal`。JSON-RPC 请求字段不能指定 principal。无身份时返回 `-32001`。stdio 演示必须显式传 `--allow-local-dev-principal`。Web/MCP CLI 和 README 已更新对应命令。

## 验证与限制

负例回归覆盖匿名 HTTP 搜索/证据读取、伪造 `X-User-ID`/`X-Papertrail-Principal` 与 JSON body、provider 返回空值、非 loopback 演示请求，以及 MCP JSON-RPC 伪造用户字段。既有 ACL 正例改为使用固定 trusted provider 或显式 loopback demo 开关。

这只是 Principal 的服务端注入边界，不是生产认证集成。部署方仍须实现并验证可信认证中间件/Principal provider；不能把 loopback `local-dev` 演示身份配置到公网、多用户反向代理或不可信共享环境。
