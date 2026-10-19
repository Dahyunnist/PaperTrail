# S2 学习记录：本地向量候选、混合排序与 OCR 回退

## 目标与范围

在 S1 的可追溯 FTS5 基线上，增加本机向量候选和 BM25/向量 Reciprocal Rank Fusion（RRF），并在同一 31 道可回答黄金题上对照。索引新增内容时，向量制品依据索引修订号失效并重建。低文本 PDF 可选择尝试本机 OCR；OCR 文本要与原生 PDF 文本区分，不能直接变成引用。

## 本地向量实现

`papertrail/retrieval.py` 使用字符 n-gram TF-IDF 特征，再以 TruncatedSVD 投影为 96 维 LSA 向量，余弦相似度排序。字符 n-gram 可处理中文连续文本和英文术语；它是分布式词项特征，不是预训练神经语义模型，不能预期具有真实语言理解能力。模型和向量以 joblib 存入 `.local/`，与源 PDF 分离。索引包含 12,857 个文本块，潜在向量累计解释方差 53.6%。

RRF 合并 BM25 与潜在向量候选，当前权重 BM25 2.0、向量 0.5，常数 60。`app_metadata.index_revision` 在新增索引内容后更新，重检时发现制品版本过期则重建。增量索引不会修改源 PDF。命令示例：

```powershell
python -m papertrail vector-build --db .local/papertrail-s1-final.sqlite3
python -m papertrail search --db .local/papertrail-s1-final.sqlite3 --query "TabDDPM categorical diffusion" --mode vector --limit 5
python -m papertrail search --db .local/papertrail-s1-final.sqlite3 --query "TabDDPM categorical diffusion" --mode hybrid --limit 5
python -m papertrail.evaluate --compare --db .local/papertrail-s1-final.sqlite3 --gold evals/gold.jsonl --k 5 --trace-out .local/s2-retrieval-comparison.json
```

## 黄金集对照

31 道可回答题，top-5 至少命中一个人工标注目标证据页为 page Recall@5。MRR 取首个目标页排名倒数；nDCG 将标注目标页作为相关结果。查询耗时是当前机器、模型已建成后的进程内热查询均值，不包括首次模型训练和装载成本。

| 模式 | page Recall@5 | MRR@5 | nDCG@5 | 平均查询耗时 |
|---|---:|---:|---:|---:|
| BM25 | 32.3% (10/31) | 0.255 | 0.337 | 11.5 ms |
| 潜在向量 | 19.4% (6/31) | 0.103 | 0.138 | 58.5 ms |
| 加权混合 | 32.3% (10/31) | 0.161 | 0.276 | 142.9 ms |

混合模式与 BM25 的证据页召回相同，但 MRR/nDCG 更低、耗时更高。潜在向量没有胜出，因此保留作本地检索调试，不设为默认。混合检索不因“技术更复杂”就被当作质量提升。示例查询能将 TabDDPM 原论文页提升到结果中，但相关论文仍会竞争靠前；细粒度错页仍是未解决问题。

## OCR 回退与证据安全

使用 `index --ocr-fallback` 时，解析器仅对少于 12 个文本词的 PDF 页调用 PyMuPDF OCR（底层要求本机 Tesseract 和英文语言数据）。识别成功的块写入 `text_origin=ocr_derived`，解析记录保存 OCR 页号；CLI 明确提示它们只是检索线索。S3 回答仅采用 `native_text` 块，并会核验对应 PDF 页面。OCR 初始化失败会记录到索引问题，不会静默把空页标成已解析。

当前工作机未检测到 Tesseract，因此成功识别扫描页这一路径未能在真实 OCR 引擎上验证；缺引擎处理已通过测试。当前 S1 pilot 选取的 PDF 都有原生可抽取文本，黄金检索评测未使用 OCR 文本。

## 验证、限制与决策

- 测试覆盖本地向量索引、混合结果、新增笔记后自动刷新向量制品及 OCR 引擎缺失时的错误记录。
- 对照只覆盖小型 pilot，不能推广到完整 148 个文件或其他领域；字符 n-gram LSA 仅作无模型成本候选，不等同于神经 dense embedding。
- 未实现生成式 MQE/HyDE、神经重排、付费 API 或 OCR 二进制安装。MQE/HyDE 仍需明确题型收益、时延和费用依据后再选。
- 默认搜索继续使用 BM25；S3 会以 `original_pdf + native_text` 约束证据，后续 Web 页面保留来源信号方便调试。

阶段路线与最终用户体验见[产品契约](../product-contract.md)。
