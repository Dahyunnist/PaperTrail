# PT5：公开许可来源登记

日期：2026-10-23

## 登记范围

新增 4 条候选来源；与 PT1 的 1 篇已核验真实论文合计 5 条。只登记官方 Nature / PubMed Central 文章页明确列出 CC BY 4.0 的条目。来源记录、许可核对链接和复核日期在 `configs/public-paper-license-registry.json`。

新增来源：

- [Learning to explain is a good biomedical few-shot learner](https://pmc.ncbi.nlm.nih.gov/articles/PMC11483110/)：PMC 页面列明 DOI 和 CC BY 4.0。
- [Workflow for detecting biomedical articles with underlying open and restricted-access datasets](https://pmc.ncbi.nlm.nih.gov/articles/PMC11078384/)：PMC 搜索记录列明 CC Attribution 与 DOI。
- [Enhancing Clinical Relevance of Pretrained Language Models Through Integration of External Knowledge](https://pmc.ncbi.nlm.nih.gov/articles/PMC11336492/)：PMC 权限声明列明 CC BY 4.0。
- [Ten simple rules to make computable knowledge shareable and reusable](https://pmc.ncbi.nlm.nih.gov/articles/PMC11189186/)：PMC 权限声明列明 CC BY 4.0。

PT1 已有来源为 Shumailov 等人的 [AI models collapse when trained on recursively generated data](https://www.nature.com/articles/s41586-024-07566-y)，Nature 页面列明 CC BY 4.0。该来源的 8 道本地题仍只是开发诊断集。

## 校验和边界

离线命令 `python scripts/validate_public_license_registry.py` 校验字段、许可枚举、官方域名和登记的本地 PDF 哈希。它不联网读取网页。上述 4 篇目前未导入本地文件，没有 PDF SHA-256，也没有人工确认的页码证据和黄金问题；因此只进入候选来源注册表，**没有**扩成冻结论文组基准。

真实论文基准验收仍未达成：当前可复核的本地真实论文仍为 1 篇、8 道开发题。只有完成本地 PDF 哈希与逐条页码黄金题、冻结文件清单后，才可报告扩大后的基准。

本阶段未下载 PDF、未访问私有资料、未调用模型。剩余模型 API 预算 `$0.0974504` 保持不变。
