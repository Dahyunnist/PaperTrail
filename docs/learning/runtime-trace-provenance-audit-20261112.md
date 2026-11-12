# 运行追踪与清单审计（2026-11-12）

运行时原先没有共享事件写入器；`run_manifest.py` 只校验静态 JSONL。清单已有 Git、数据集、提示词、评分器、切分、运行环境、预算、费用、状态和时间字段，但部分字段缺少值域校验。

现新增可选 JSONL 追踪：显式设置 `PAPERTRAIL_TRACE_JSONL` 才会写入。记录 `run_id`、`trace_id`、`span_id` 和时间戳；事件只接受固定标量字段，不保存问题、提示词、文档文本、引用原文、文件路径、用户 ID 或密钥。未配置时不创建文件。

六类运行时事件：`retrieval.completed`、`rerank.completed`、`generation.completed`、`citation.validated`、`access.checked`、`human.reviewed`。QA 调用绑定同一 run/trace 标识；检索、引文验证、授权读取/搜索及人工立场标注在对应代码路径发出事件。生成失败也记录失败状态。离线静态样例覆盖六类事件。

清单校验现在检查 Git SHA、非空 split、状态枚举、时间戳及非负预算值；仍保留 synthetic-only、离线模型为空、费用为空、SHA-256 与敏感字段校验。

验证：`tests/test_run_manifest.py`、`tests/test_runtime_trace.py`、`tests/test_pt3_citation_failure_paths.py`、`tests/test_access_control.py` 共 14 项通过。全部使用合成或既有测试夹具；没有模型调用，也没有读取私有材料。
