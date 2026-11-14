# PT-1 数据准备链路审计（2026-11-14）

## 来源与许可元数据

PT-1 冻结来源清单记录 30 个唯一 DOI。每条均登记 CC BY 4.0、公开文章记录、许可证据/政策链接、下载链接、本地 PDF SHA-256 及来源版本；本轮只读这些 JSON 元数据，没有打开 PDF，也没有在线重新核验许可页面。3 条来源缺少 `source_version`，此前冻结导出保留为空，不能据此推断版本。

空白任务 CSV 与来源清单 SHA-256 固定在按 DOI 分组的 frozen manifest 中。现有 `export_pt1_dual_annotation_tasks.py validate` 可只读取任务 CSV 和 JSON 清单完成版本/分组校验，不打开 PDF。

## 按论文分组与 split 边界

冻结批次为 40 题、30 个 DOI，所有任务行与来源记录均为 `development_seen`，同一 DOI 的题目归入同一 paper group。PT-1 gold schema/import 校验只接受 `development`，候选来源校验只接受 `development_seen`；当前 PT-1 批次不能混入 test/heldout split。

只用来源 manifest 的 DOI 与 split 元数据，对比仓库已有 PT5–PT18 来源清单：PT-1 与 PT5、PT6、PT7、PT8、PT9、PT10、PT11、PT12、PT13、PT18 各有 3 个 DOI 重叠；与 PT14、PT15、PT17 未见 DOI 重叠。由于其中包含历史 heldout 集，这 30 篇都必须继续视作已见开发来源；不得将 PT-1 或历史指标描述为跨基准独立盲测，也不得把重叠数据合并后声称 paper-level holdout。该检查只比较仓库内来源登记，不证明所有外部数据集均无重叠。

## 双人输入、仲裁与评估

- A/B 两份填写 CSV 可直接交给 `validate_pt1_dual_annotations.py`。校验器逐行核对任务 DOI/SHA、双人独立声明、页码和精确 PDF 字符 span；输出报告只保留 task 状态、冲突字段与 annotator ID，不输出答案或引文。
- 双人 CSV 校验通过不等于 gold 已裁定。意见冲突需人工仲裁；无冲突也仍需复核。校验器不会合并答案或证据。随后由人工整理为 PT-1 v2 JSONL，再运行 gold validator/importer。单 CSV importer 接收的是已通过独立 reviewer 的最终审阅表，不是原始 A/B 双人表。
- schema 将证据定义为数组，每条绑定 DOI、PDF SHA、物理页、精确字符 span、quote 和 relation；`minimumCompleteEvidenceSet`/`minimum_complete_evidence_set` 要求人工显式确认完整最小证据集合。v2 校验会要求跨论文/多跳题至少两篇来源，冲突题同时包含支持和反驳证据。
- retrieval evaluator 已逐条检查 evidence quote 是否出现在命中的对应 SHA/页，并提供 `complete_evidence_at_k`、`evidence_item_recall_at_k` 与 `all_evidence_pages_at_k`。现有 QA 评估测试也覆盖多来源预期页覆盖与错误 quote 不算精确证据。双人文件本身先经独立校验和人工仲裁，不直接作为运行 gold。

## 边界与下一步

PT-1 仍为 0/40 人工 gold。两位标注者需分别完成 A/B 表；收到文件后先跑双人校验与仲裁状态报告，不能在冲突未处理时导入。现阶段没有新增题目、真实 gold、来源全文或 PDF 内容，也没有模型请求。许可页面的当前有效性与仓库外跨集合重叠仍需在真正发布盲测集前单独确认。
