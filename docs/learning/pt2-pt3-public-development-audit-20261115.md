# PT-2/PT-3 公开开发集离线诊断（2026-11-15）

## 范围与隔离

只读取已登记的 PLOS CC BY 4.0 PT7、PT8、PT10、PT11 开发组，共 18 题、12 篇 PDF。脚本逐项核对来源与 gold SHA，在系统临时目录重建索引；不读取 `.local`、PT-1 文件、私人 PDF 或其他评测组。冻结 gold 未修改，所有步骤不调用模型。

复现：

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_pt2_pt3_public_development.py
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_pt2_pt3_public_development_audit.py
```

机器结果见 `evals/pt2-pt3-public-development-diagnostic-20261115.json`。

## 按题型结果

| 题型 | 题数 / 证据槽 | 完整候选题数 @20 / @40 / @80 | 命中金标页 / 页含金标短语 | 观察 |
|---|---:|---:|---:|---|
| fact_location | 12 / 12 | 10 / 12 / 12 | 8 / 12；5 / 12 | 候选深度 40 已覆盖本开发集全部事实定位题；提到 80 无增益。 |
| cross_paper | 3 / 6 | 1 / 1 / 3 | 2 / 6；0 / 6 | 深度 80 补齐候选页，但 extractive 引文均未包含 gold 短语。只加深检索不足以修复引文选择。 |
| multi_hop | 1 / 2 | 1 / 1 / 1 | 0 / 2；0 / 2 | 候选页全有，但 `ask(generate=False)` 没选中 gold 引文，损失在摘录选择。 |
| unanswerable | 2 / 0 | 不适用 | 不适用 | 两题都有 extractive 候选；这不是错误拒答证据。生成关闭，拒答质量不可测。 |

事实定位数据的候选完整度支持把深度 40 作为后续开发实验起点，但当前引用短语只命中 5/12，且没有独立数据验证，故不改默认参数。跨论文深度 80 的候选完整覆盖虽升至 3/3，引用短语仍为 0/6；不做只增加候选数的产品改动。PT-3 的真实拒答、语义支持与答案正确性需要人工复核或获准模型实验，本轮不能推断。

## 评测边界与回归

报告分开记录完整候选覆盖、最终摘录页命中和 gold 短语包含；页级命中不冒充语义支持。对不可答题只报告“有无 extractive 候选”，`refusal_quality.status=not_assessed_without_generation`。现有 `tests/test_evaluate_qa.py` 和 `tests/test_pt3_adversarial_synthetic.py` 锁定 `budget_blocked` 不计正确拒答；本轮不重新生成回答。

新增审计脚本的测试确认来源组限于四个开发组、来源哈希通过、模型调用守卫生效，且候选深度与拒答指标口径不混淆。此开发集已见，报告不是盲测或泛化结论。PT-1 继续暂停，仍为 0/40。
