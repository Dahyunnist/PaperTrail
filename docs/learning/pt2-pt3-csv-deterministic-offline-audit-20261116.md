# PT-2/PT-3 CSV 与确定性评测离线核对（2026-11-16）

复核范围：PT-1 CSV 导入器的合成拒绝路径、PT-2 synthetic frozen runner 和 manifest-bound 无模型评测 runner。定向命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q tests/test_pt1_human_csv_import.py tests/test_evaluate_run.py tests/test_pt2_synthetic_retrieval.py
```

结果：**26 passed**。测试即时生成临时 PDF、CSV、manifest、runtime gold 和索引。CSV 负例涵盖重复任务 ID、annotator/reviewer 相同或未审、来源 SHA 变化、页码/精确 span 不匹配、多论文题型越界及失败时不落输出。评测 runner 核对 manifest hash、gold path/hash/count、no-model usage、报告确定性及隐私字段过滤。PT-2 runner 两次重建 synthetic input，逐行报告和 report SHA 一致。

这些回归证明输入契约与报告生成可复现，不证明标注内容正确、检索质量或回答质量。没有载入、修改或核验仓库真实 gold；没有读取私人 PDF 或调用模型。PT-1 仍暂停。真实双标与仲裁、PT-2 独立真实论文完整证据覆盖、PT-3 真实回答/拒答/冲突质量仍需人工 gold。

## 拒答与引用回归补充

追加运行 CSV 导入、manifest-bound runner、PT-2 frozen synthetic、QA evaluator、PT-3 citation failure 和 QA 行为测试：**69 passed**。

本轮仅测试临时目录生成的 CSV/PDF/manifest/gold/索引。覆盖 no-model 成本与输入 hash 绑定、报告重复运行一致性、跨来源/跨页证据槽、精确引文与来源 SHA/页码/chunk 校验、无证据拒答、错误空拒答、部分回答和预算阻断分类。跳过读取仓库正式 gold、私人 PDF 的测试及公开集重评；没有生成或改写 gold，也没有模型调用。

人工依赖项保持 blocked：PT-1 双标与仲裁；PT-2 独立真实论文的最小完整证据集及检索质量；PT-3 语义支持/冲突判断、正确拒答率、错误作答率和引用语义准确率。需要人工逐题标注问题可回答性、最小完整证据 span、答案 claims 与支持/矛盾/不足关系，并由第二位标注者独立复核，分歧交仲裁。现有合成回归只证明程序契约，不替代这些 gold 或指标。
