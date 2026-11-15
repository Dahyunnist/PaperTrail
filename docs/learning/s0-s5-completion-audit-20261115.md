# S0–S5 阶段完成状态审计（2026-11-15）

本索引按当前代码和可定位测试记录阶段状态。它不把已实现功能等同于完整验收；不启动 PT-1 人工标注，不进入 PT-5。

| 阶段 | 状态 | 代码与测试证据 | 未完成边界 |
|---|---|---|---|
| S0 资料盘点与 gold 指针 | 已交付，含人工复核项 | `papertrail/audit.py`、`papertrail/gold.py`；S0 gold 引文校验记录见 `docs/learning/stage-S0.md` | 两组版本候选和网页拦截页仍需人工确认；不据页文本比例宣称解析质量完成。 |
| S1 解析与 BM25 基线 | 基线已交付 | `papertrail/s1_index.py`；`tests/test_s1.py` 覆盖 SHA、版本、页码、更新/删除、事务回滚和重试 | 只覆盖选定 pilot；表格结构、复杂版本谱系和真实语料全面召回仍未验收。 |
| S2 向量、混合与 OCR | 能力已实现，实际 OCR 引擎验证未完成 | `papertrail/retrieval.py`；`tests/test_s1.py` 与向量回归覆盖本地制品刷新；`stage-S2.md` 记录 Tesseract 不可用 | 当前默认仍为 BM25；LSA 不等同神经 embedding；扫描页 OCR 成功路径未在真实引擎验证。 |
| S3 引文约束 QA | extractive 安全路径已交付；生成质量未验收 | `papertrail/qa.py`；`tests/test_s3.py` 覆盖精确引文、来源哈希、页码、持久化和源篡改拒答 | 不把来源正确当作语义支持；PT-2/PT-3 cross-paper extractive phrase 仍为 0/6；真实 holdout 未验收。 |
| S4 跨论文证据比较 | 候选收集与人工标注流程已交付 | `papertrail/compare.py`；`tests/test_s4.py` 覆盖双论文证据、标签与 gap 关联 | 关键词共现只产生候选；尚无自动立场判断或人工评审规模验收。 |
| S5 本机 Web 工作台 | 本机闭环已交付，部署边界明确 | `papertrail/web.py`、`papertrail/jobs.py`；`tests/test_s5_web.py`、`tests/test_jobs.py`；PT-4 ACL 生命周期和 Web/MCP 集成回归见 `tests/test_pt4_acl_retrieval_regressions.py`、`tests/test_access_control.py` | 未验证生产身份、跨进程 worker、远程部署或多租户隔离；仅作本机单用户应用。 |

## PT-4 最近验证

- Web 页面实际呈现已核验片段、版本、PDF 页码和覆盖状态；脱敏 answer-eval JSONL 校验 owner、SHA、页码和片段，不含本机路径。
- Web 直接读取、MCP 资源读取与 collection ACL 用合成数据交叉验证，授权 owner 成功，其他 owner 拒绝。
- 更新、删除、增量重建和任务恢复有独立合成回归；不读取私人 PDF，不调用模型。
- 最新定向 Web/eval/MCP 集成测试：6 passed；最近索引/ACL/PT-4 相关套件：70 passed。旧 S0–S5 文档中的阶段测试计数是历史记录，不应当作当前全量测试计数。

PT-1 仍暂停。PT-2/PT-3 公开开发集只作诊断，不能替代冻结 holdout。当前不启动 PT-5。
