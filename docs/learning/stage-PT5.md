# PT5：公开许可论文组与页级黄金题

日期：2026-10-23

## 冻结范围

冻结组 `pt5-public-real-20261023` 含 3 篇公开论文、6 道人工编写题，每篇 2 题。三篇均由 PLOS 官方出版者端点下载，官方文章页标明 CC BY 4.0。PDF 来源版本、官方记录、许可证据、下载地址、本地路径及 SHA-256 均登记在 `configs/public-paper-license-registry.json` 与 `evals/pt5-public-source-manifest-20261023.json`。

| 论文 | 来源版本 | PDF 页数 | SHA-256 |
|---|---|---:|---|
| Workflow for detecting biomedical articles with underlying open and restricted-access datasets | 版本记录；2024-05-08 | 20 | `2aa23da30ca26e61ecff0389045f2f04110f093343b60312144211037b20baa4` |
| Ten simple rules to make computable knowledge shareable and reusable | 版本记录；2024-06-20 | 9 | `e887af39e1982b7e164100bf591409340fdbed78153fc11f8a04696518123122` |
| Ten quick tips for ensuring machine learning model validity | 版本记录；2024-09-19 | 12 | `176e2321b47a2cf1c726372eafeb24f47b73e9b3d75c91c98545af4dcc5835b5` |

公开出版者记录：[Workflow](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0302787)、[Computable knowledge](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1012179)、[Machine-learning validity](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1012402)。每篇页面列出 DOI 与 CC BY 4.0 许可。语料仅从上述官方出版者页面下载，不含私人 PDF。

## 黄金题与复现

题目位于 `evals/pt5-public-gold-20261023.jsonl`，来源配置位于 `evals/pt5-public-sources.yaml`。每题证据指针绑定来源 ID、文件名、SHA-256、PDF 物理页码和短引文。每篇所用原文摘录总长少于 25 个英文词；题目按论文分组，不跨组复用证据。

```powershell
.\.venv\Scripts\python.exe scripts/validate_public_license_registry.py
.\.venv\Scripts\python.exe -m papertrail.gold --sources evals/pt5-public-sources.yaml --gold evals/pt5-public-gold-20261023.jsonl --minimum-questions 1
```

冻结清单同时记录黄金文件 SHA-256、问题数和来源 PDF 哈希。验证器逐页抽取 PDF 并比对引文；它不调用模型。`fetch_pt5_public_group.py` 仅允许 CC BY 4.0 与 PLOS 官方域，校验 PDF MIME、文件头、重定向域和哈希，并拒绝写出项目目录。

## 排除项与范围

另外两篇候选的许可虽已核验为 CC BY 4.0，但官方 PDF 端点分别返回浏览器 PoW 页面/403 和空 HTTP 202，故未纳入冻结组；没有尝试绕过验证，也没有使用第三方镜像。PT1 的 Nature 论文仍是另一组 8 题开发集，不计入本组。

PT5 目前只有 3 篇论文、6 道题，是可复现的公开论文小型诊断组；不能据此宣称独立测试集、广泛论文覆盖或泛化能力。PT1–PT3 的评测与账本未改动，本阶段没有模型调用，API 预算仍为 `$0.0974504 / $0.50`。
