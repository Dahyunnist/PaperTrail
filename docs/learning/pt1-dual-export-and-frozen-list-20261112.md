# PT-1 双人填写导出与论文分组冻结清单

## 现有覆盖核对

既有匿名最小包含 **40 题、30 篇不同来源**，符合“40题、30–60篇”计划；状态仍为 `pending_human_annotation`。新导出保留两份相同的独立填写表和一份按 DOI 分组的来源冻结清单。旧匿名包继续保留，不被新公开来源元数据替换。

填写表是本机公开来源审阅版，包含 DOI、题名、来源记录/下载链接、PDF SHA、许可证声明及许可证证据链接；不包含 `local_pdf` 路径或 PDF 正文。它不是匿名包。A/B 两份 human 字段均为空，须分开交给两位标注者，勿让其中一人查看另一份答案。表格包含题型、问题、答案性、答案/拒答理由、最小证据集 JSON 和独立性声明字段。

## 已生成文件

- `evals/pt1-dual-annotation-40-20261112-a.csv`
- `evals/pt1-dual-annotation-40-20261112-b.csv`
- `evals/pt1-dual-annotation-40-20261112-frozen-grouped.json`

冻结清单覆盖40题、30篇论文，按 DOI 分组，记录题目 ID、split、PDF SHA、公开来源、许可版本、许可声明和证据 URL。输入 CSV 与来源 manifest 的 SHA 固定在清单中；改动来源或题目后须重新导出并重新冻结。

源 manifest 中有 3 篇缺 `source_version` 字段。导出按原数据留空，没有猜补。每个来源的其余必要许可/来源记录字段均已核对非空。该校验确认字段及其与源 manifest 的一致性，不独立证明许可证声明本身真实或仍有效。

## 重新导出与校验

```powershell
.\.venv\Scripts\python.exe scripts/export_pt1_dual_annotation_tasks.py export --tasks evals/pt1-human-annotation-task-40-20261111.csv --manifest evals/pt1-candidate-manifest-20261111.json --output-dir evals --prefix pt1-dual-annotation-40-20261112
.\.venv\Scripts\python.exe scripts/export_pt1_dual_annotation_tasks.py validate evals/pt1-dual-annotation-40-20261112-frozen-grouped.json --tasks evals/pt1-human-annotation-task-40-20261111.csv --manifest evals/pt1-candidate-manifest-20261111.json
```

填完后，两份 CSV 可直接交给双人校验器；`evidence` 列须填符合 schema 的 JSON 数组，不可答记录用空数组：

```powershell
.\.venv\Scripts\python.exe scripts/validate_pt1_dual_annotations.py evals/annotator-a-filled.csv evals/annotator-b-filled.csv --tasks evals/pt1-human-annotation-task-40-20261111.csv --manifest evals/pt1-candidate-manifest-20261111.json --report .local/pt1-adjudication-status.jsonl
```

双人校验器会在有标注后读取 manifest 所列来源 PDF，核验 SHA、物理页码和 span；本次冻结清单校验只读 CSV 与 JSON 元数据，没有打开 PDF。冲突保持 `pending_adjudication`，不得合并或猜答案。PT-1 gold 继续待双人完成，不运行模型评测。

定向回归命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .tmp/pytest-pt1-delivery tests/test_pt1_dual_task_export.py tests/test_pt1_dual_annotation_validator.py tests/test_pt1_human_annotation_task.py tests/test_pt1_human_csv_import.py tests/test_pt1_gold_jsonl_validator.py tests/test_pt1_minimal_annotation_package.py
```

本轮 **36 passed**。覆盖测试使用合成元数据、临时合成 PDF 与空白任务模板；30/40 核对只读现有匿名包、CSV 和 manifest，不读 PDF、不填答案。PT-2 合成回放只作为可复现技术证据，不外推为真实论文质量提升。
