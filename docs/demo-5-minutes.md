# PaperTrail 五分钟演示

## 0:00–1:00：看清评测边界

打开 `docs/learning/stage-PT1.md`。说明私有文献没有上传；许可证可明确核验的真实论文只有 1 篇，因此 8 题仅作本地开发诊断，没有真实论文测试集。

## 1:00–2:00：核验冻结合成集

```powershell
python -m papertrail.gold --sources evals/fixtures/pt3-synthetic/sources.yaml --gold evals/pt3-synthetic-gold-20261023.jsonl --minimum-questions 1
```

展示两个合成 PDF、manifest 中的 SHA-256 和页码证据。所有题目和引用均为人工构造内容。

## 2:00–3:30：查看回答、引用与缺项

打开 `reports/pt3-synthetic-model-20261023.json`。先看样本量和跨论文比较，再看只回答已支持样本量、并点明随访时长缺失的部分答案。随后展示正确拒答案例。

## 3:30–4:30：复核引用

```powershell
python scripts/verify_pt3_report.py
```

说明脚本检查每条 claim 的来源哈希、物理页码、原文短引文和 native/OCR 来源标记。PT3 共检查 18 条 claim-证据指针。

## 4:30–5:00：展示真实集失败和边界

打开 `docs/learning/stage-PT2.md`。BM25 在 8 题上找齐 gold 页，但完整引文集合只有 4/8；RRF 没改善完整证据覆盖。最后展示 PT3 中“delivery time”被误译为“分娩时间”的失败，强调自动支持审查不能替代人工语义复核。
