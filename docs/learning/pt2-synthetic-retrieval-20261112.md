# PT2 合成检索闭环（2026-11-12）

## 范围

本轮只用 `scripts/evaluate_pt2_synthetic.py` 在临时目录运行时生成的 3 个合成 PDF。冻结集含 3 个 query：两个单证据 query、一个双证据比较 query。测试明确传入合成来源配置和选择清单；不读取 `.env`、本机来源 manifest 或私人 PDF。没有调用模型或联网。

## 结果

| 检索模式 | 完整证据集合 | 查询数 | 结论 |
|---|---:|---:|---|
| BM25 | 3/3 | 3 | 全部 gold 最小证据均在 top-20 |
| dense（本地字符 TF-IDF + SVD 向量） | 3/3 | 3 | 全部 gold 最小证据均在 top-20 |
| RRF（BM25 + 本地向量） | 3/3 | 3 | 全部 gold 最小证据均在 top-20 |

JSONL 报告逐项记录冻结题 ID、query SHA、gold evidence、命中证据排名与检索分数、缺失证据和失败归因：`evals/pt2-synthetic-retrieval-report-20261112.jsonl`。当前没有失败项，故失败归因为空。冻结 query/gold SHA-256：`003e7b11fc8ce3309cc12df140ce408b8f3f42ba58d52a4e093d0832c70a6269`。

测试验证 3 种模式全覆盖、排名分数存在、冻结集 SHA 固定、同一合成夹具重复运行得到相同 JSONL 和报告 SHA、比较 query 命中现有拆题触发条件，以及评测脚本不含网络导入。报告分数保留 4 位小数，以避免不同 BLAS 实现的末位浮点差异改变报告哈希；检索排名仍由完整精度分数决定。运行命令：

```powershell
python scripts/evaluate_pt2_synthetic.py --fixture-dir .tmp/pt2-synthetic-run --output .tmp/pt2-synthetic-run/results.jsonl
python -m pytest -q -p no:cacheprovider --basetemp .tmp/pytest-pt2 tests/test_pt2_synthetic_retrieval.py
```

## 限制

这是端到端离线合成回归，不是真实论文评测、盲测或泛化证据。这里的 dense 明确指本项目现有字符 TF-IDF + SVD 向量检索，不是神经 embedding 或 BGE。证据集合判定基于合成 PDF 中预先固定的短语，不评估答案生成、模型拆题质量、引用真实性或真实文献难度。现有问答证据槽测试仍覆盖槽映射和缺项拒绝；本轮仅检查比较 query 的拆题触发，不调用问答模型流程。
