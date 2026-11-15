# PT-2 冻结合成检索复跑核对（2026-11-15）

## 冻结输入与指标

`scripts/evaluate_pt2_synthetic.py` 内冻结 3 个合成 query、2 条目标 evidence phrase；runner 临时生成 3 份合成 PDF。BM25、字符 TF-IDF + SVD dense、RRF 各跑 3 题，共 9 个方法/题目结果。`tests/test_pt2_synthetic_retrieval.py` 重建两次索引和报告，核对输入 SHA、每组完整证据集合、命中排名/分数及逐行报告和 SHA 一致。

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q tests/test_pt2_synthetic_retrieval.py
```

结果：**3 passed**。本轮与 PT-3 页码边界回归合跑为 **4 passed**。测试没有加载仓库真实 gold、私人 PDF 或外部服务。

## 判断与边界

冻结合成输入可重复生成相同确定性报告；9/9 结果覆盖合成最小证据集合。该比例只描述这 3 个人工构造 query，不代表真实语料检索质量。`dense` 是字符 TF-IDF + SVD，不是神经 embedding；单机重复也不证明跨硬件数值一致。

下一具体缺口：PT-1 仍暂停，故没有独立人工双标集可验证真实 PT-2 完整证据覆盖。保持默认检索策略不变；待 PT-1 解冻后再做独立数据验收。本轮不读或改真实 gold，不读私人 PDF，不调用模型。
