# PaperTrail PT-1～PT-4 路线审计与 PT-1 候选批次

审计依据：`Agent四项目_JD对标与升级路线_2026-10-23.md` 第七、八节。代码基线 `c2125f9a5ad169104c84a8a6e0c2d52646da19f3`。

## 路线审计矩阵

| 阶段 | 状态 | 证据与缺口 |
|---|---|---|
| PT-1 真实论文基准 | 部分 | `evals/pt9-pt12-final-heldout-gold-20261023.jsonl` SHA-256 `e03aaec49d953664841ab9cf3e17f079829597dc2200e8c071e1d80f9c1b510c`，12 题/6 篇；按路线仍低于 40 题/30 篇。PT5 是 6 题小组。本文冻结 6 个已见来源，0 个 gold 标注。 |
| PT-2 完整证据检索 | 部分 | `docs/learning/final-public-holdout-evaluation-20261023.md` SHA-256 `d6274ed33b77c35ec91589dca7cee01624cc30353f8623f7ccacd77793fbd590`；混合检索完整证据覆盖 7/10 可答题，跨论文完整覆盖未达标。已有 BM25/vector/RRF 与追踪，需新独立真实集复验。 |
| PT-3 可信回答/错误拒答 | 部分 | `evals/pt17-model-e2e-analysis-20261023.json`：4 道可答题完整回答 0；候选证据槽 6/7、筛后 3/7、引用 1/7；不可答有效拒答 0/1。`tests/test_s3.py` 覆盖合成边界，不等于真实论文达标。 |
| PT-4 权限、索引、Web 评测 | 部分 | `docs/upgrade-roadmap.md` 记载本地 Web、MCP、索引队列/恢复；尚缺多用户 ACL 隔离实测及 Web 评测审阅验收证据。 |

## PT-1 候选批次

新增 `evals/pt1-candidate-manifest-20261111.json`，包含 6 篇 PLOS Computational Biology 论文；均为已见开发来源，不能作为盲测。官方文章页写明 Creative Commons Attribution License；PLOS 链接的许可文本标识 CC BY 4.0。论文均已在 PT18 研发过程中查看，故冻结为 `development_seen`，不能作为盲测。PDF 保留于 `.gitignore` 忽略的本机目录，不提交全文。

| DOI | 标题 | SHA-256 | 许可与来源 |
|---|---|---|---|
| `10.1371/journal.pcbi.1013657` | Ten simple rules for making biomedical data resources accessible | `fd90106cc19e5a587bf0355822563d1681cf556eaaa92373823d0e84c6a9230e` | [PLOS 文章](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1013657)，[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| `10.1371/journal.pcbi.1013970` | Ten simple rules for building a collaborative coding culture | `0b21626f7223a66c7edc4628cd883a568e411067745afc3f055683f4b9643445` | [PLOS 文章](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1013970)，[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| `10.1371/journal.pcbi.1014882` | Ten simple rules for responsible use of AI and LLMs in computational biology | `6992aafd1be44a31c70d1dc080691d75eb9cfe50470ad686b65df6143f6b6871` | [PLOS 文章](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1014882)，[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| `10.1371/journal.pcbi.1005412` | Ten simple rules for making research software more robust | `002081be65fbd42c0356d3e49ac7f49fa6202f566f50341481ead22d3cce78b2` | [PLOS 文章](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005412)，[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| `10.1371/journal.pcbi.1010879` | Ten (not so) simple rules for clinical trial data-sharing | `950c43a35649934f2375e745c792a599225e0838e9fc1527c3df5829c9b3877f` | [PLOS 文章](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1010879)，[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| `10.1371/journal.pcbi.1006561` | Ten simple rules for documenting scientific software | `c2b50ad022577a957672622dec9ae0ad7ab746ef38a04ab051f007814fb76e7d` | [PLOS 文章](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1006561)，[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |

gold schema 在 `evals/pt1-gold-schema-v1.json`。空文件 `evals/pt1-candidate-gold-20261111.jsonl` SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`；当前 0 题、0 人工标注。下阶段须人工逐题写最小完整证据集合、页码、字符 span、引文和来源哈希，再双人复核后冻结。

运行 `python scripts/validate_pt1_candidate_manifest.py` 可核验来源数量、DOI 唯一性、状态、PDF 路径/哈希、空 gold 哈希和 schema。当前结果：通过，6 个来源，0 条标注。校验器支持临时项目目录；定向测试覆盖 PDF 哈希篡改。

本阶段未调用模型。账本上限 `$0.50`、历史已用约 `$0.44008`；剩余额度保留，不用于此阶段。PT-1 规模目标仍未完成。


## PT-2/PT-3 与测试边界

本轮未改冻结评测基线。PT-2 完整证据覆盖仍为 7/10；PT-3 真实集完整可答回答仍为 0/4、不可答正确拒答为 0/1。定向回归 `tests/test_s3.py` 与 `tests/test_p13_regressions.py`：41 项通过。

全套测试在受限运行中为 75 项通过、1 项受本机回环权限拦截：`tests/test_local_llm.py::test_local_chat_client_uses_loopback_ollama_json_api`。本地假服务绑定 `127.0.0.1` 的临时端口；连接失败链为 `urllib.error.URLError`，底层 `WinError 10013`（套接字访问被拒），最终 `papertrail/local_llm.py:82` 抛出 `RuntimeError`。该用例获准单独运行后通过；不涉及外网或模型。PT-1 定向测试为 2 项通过。
