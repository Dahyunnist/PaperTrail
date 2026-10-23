# PT9 + PT12：最终一次性 holdout 评测

日期：2026-10-23

## 冻结范围与执行

PT9、PT12 共含 6 篇此前未用于开发诊断的论文和 12 道冻结题。题集包括事实定位、跨论文、多步和不可回答题；13 条页级黄金证据绑定冻结 PDF SHA-256。两组黄金集单独哈希及合并哈希见评测 JSON。

完整公开索引含 30 篇论文、352 个 PDF 页、841 个解析段和 4553 个文本块，解析器为 `papertrail-s1-4`。索引仅使用已登记的 CC BY 4.0 官方来源。PT6 是先前已暴露组，只作语料中的背景文档；PT6 结果未用于调参。

本阶段运行 BM25、字符 TF-IDF + SVD 向量和 RRF 混合检索，分别取 k=5、k=10。问答摘录路径使用 `generate=False`，没有模型或 API 调用。评测完成后未再调参。

## 检索结果

页面 Recall 统计 10 道可回答题中至少命中一个目标页的比例。完整证据表示同一题的全部黄金证据页均被覆盖；Evidence-item Recall 衡量 13 条黄金证据片段的命中比例。

| k | 模式 | 页面 Recall | MRR | 全部证据页覆盖 | 完整题覆盖 | Evidence-item Recall |
|---:|---|---:|---:|---:|---:|---:|
| 5 | BM25 | 0.600 | 0.315 | 0.600 | 0.500 | 0.462 |
| 5 | 字符 TF-IDF + SVD | 0.400 | 0.192 | 0.400 | 0.300 | 0.308 |
| 5 | BM25 + 向量 RRF | 0.600 | 0.312 | 0.600 | 0.500 | 0.462 |
| 10 | BM25 | 0.700 | 0.329 | 0.700 | 0.600 | 0.538 |
| 10 | 字符 TF-IDF + SVD | 0.700 | 0.231 | 0.500 | 0.500 | 0.538 |
| 10 | BM25 + 向量 RRF | 0.700 | 0.395 | 0.700 | 0.700 | 0.615 |

k=10 混合检索为最佳完整证据覆盖：7/10 道可回答题覆盖所有黄金页。事实定位命中 6/7，多步题命中 1/1；两道跨论文题均未覆盖全部目标页。PT9-05 的统计不确定性证据页，以及 PT12-05 的一侧跨论文证据页也未命中。

## 最终引用路径

12 道题全部返回 `verified_excerpts`，模型名为空。最终摘录只覆盖 5/11 个不同黄金证据页；与黄金短引文逐字相同的引用为 0/13，另有 3/13 条黄金短引文包含在较长显示片段中。

两道不可回答题也各自返回候选摘录。因为这次关闭生成模型，结果只评估证据摘录，不代表生成回答的拒答能力；当前摘录路径本身不会替用户判断候选证据是否足以回答。

## 结论与边界

30 篇论文、50 道题达到 PT1 预设公开语料规模下限。该规模仍小，主题集中于计算生物学和科研实践。测试仅支持这 6 篇论文、12 道冻结题上的离线检索结论，不支持跨领域泛化。

PT9 与 PT12 已各完成一次合并测试，不再称为盲测。测试后没有调整系统，也没有复跑测试。PT6 暴露组与 PT9/PT12 独立测试角色保持区分。

## 复现

```powershell
.\.venv\Scripts\python.exe -m papertrail.gold --sources evals/pt-public-all-sources-20261023.yaml --gold evals/pt9-pt12-final-heldout-gold-20261023.jsonl --minimum-questions 12
@'
import hashlib, json
from pathlib import Path
import yaml
config = yaml.safe_load(Path('evals/pt-public-all-sources-20261023.yaml').read_text(encoding='utf-8'))
rows = []
for root in config['roots']:
    for path in sorted(Path(root['path']).glob('*.pdf')):
        rows.append({'root_id': root['id'], 'file_name': path.name,
                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'kind': 'pdf', 'source_type': 'original_pdf',
                     'relative_path': path.name})
Path('.local/pt-public-all-selection-20261023.jsonl').write_text(
    ''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
print(f'selected_pdfs={len(rows)}')
'@ | .\.venv\Scripts\python.exe -
.\.venv\Scripts\python.exe -m papertrail index --sources evals/pt-public-all-sources-20261023.yaml --selection .local/pt-public-all-selection-20261023.jsonl --db .local/pt-public-all-20261023.sqlite3
.\.venv\Scripts\python.exe -m papertrail vector-build --db .local/pt-public-all-20261023.sqlite3 --artifact .local/pt-public-all-20261023.vectors.joblib
.\.venv\Scripts\python.exe -m papertrail.evaluate --compare --db .local/pt-public-all-20261023.sqlite3 --gold evals/pt9-pt12-final-heldout-gold-20261023.jsonl --k 10 --minimum-questions 12 --modes bm25 vector hybrid --vector-artifact .local/pt-public-all-20261023.vectors.joblib
```

原始 k=5/k=10 traces 与 QA 摘录明细只保存在忽略目录 `.local/`，未提交全文检索结果。
