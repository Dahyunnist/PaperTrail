# P4 学习记录：MCP 证据接口

## 实现

`python -m papertrail mcp --db ...` 启动 stdio MCP server。服务声明 `tools` 与 `resources` 能力，实现初始化、ping、工具列表和调用、资源列表和读取。只读 SQLite 连接带 `mode=ro` 与 `query_only`，原有检索增加可选只读连接。

工具 `search_papers` 只查 `original_pdf`，返回论文 SHA、页码、章节和检索分数，不泄露本机绝对路径。`get_evidence` 校验 SHA 格式、来源文件当前哈希和页码，再返回该原文页。资源 URI 提供论文元数据和原文页。个人笔记、对话记忆和写操作不开放。

## 验证

新增 stdio 客户端测试，真实启动服务进程并走 JSON-RPC 初始化、工具列表、论文搜索、证据读取、资源列表/读取和错误分支。测试前后比较 SQLite 文件 SHA-256，确认服务没有写索引库。

```powershell
python -m pytest tests/test_mcp_server.py -q
python -m pytest -q
```

MCP 交互按官方 JSON-RPC tools/resources 形状实现；当前测试是本仓库的 wire-level 客户端，没有安装官方 Python MCP SDK。

## 经验

MCP 的 schema 与 capability 声明只是入口。还要验证真实 stdio 消息、参数边界、工具错误、资源 URI 和只读属性。引用读取重新验证来源哈希，可防止数据库里的旧路径被误当成当前证据。
