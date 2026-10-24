# 本机运行冒烟检查（2026-10-24）

## 隔离环境与启动

- Windows x64，CPython 3.12.14，与 `requirements-dev.lock` 声明环境一致。
- 用现有 CPython 创建系统临时目录下的隔离虚拟环境，按 `requirements-dev.lock` 安装成功；`pip check` 无冲突。
- 当前主机 `py -3.12 --version` 返回 “No suitable Python runtime found”。用项目已有 Python 3.12.14 创建隔离环境完成验证；未更改 README 的标准命令。
- 隔离环境中的 `python -m papertrail --help` 可启动并列出索引、检索、问答、Web、MCP 等命令。

## 离线核心流程

- 用仓库合成 PDF 建临时本机索引：2 篇文献、8 个章节、20 个片段；无解析异常。
- BM25 查询能召回目标论文和含答案的原文片段。
- 冒烟检查发现无模型 QA 对多词问题要求两个词重合，导致单个强匹配证据被误拒答。阈值改为一个词形重合，证据仍须通过来源哈希、页码和原文校验。
- 修复后，无模型 `ask` 返回 `verified_excerpts`，摘录为 “The trial enrolled 120 adults.”，对应 PDF 哈希及页码有效；不自动综合答案。
- 隔离环境全套测试：71 passed。

## 边界

- 未启动真实 Web 服务器或 MCP 客户端会话；仅验证 CLI 可导入启动。
- 未调用云模型。
- `.env`、`.local/`、健康检查数据库、PT18 PDF 与其未发布评测文件均不进入 Git。
