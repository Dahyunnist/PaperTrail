# PaperTrail PT-1～PT-4 路线审计与 PT-1 候选批次

审计依据：`Agent四项目_JD对标与升级路线_2026-10-23.md` 第七、八节。代码基线 `c2125f9a5ad169104c84a8a6e0c2d52646da19f3`。

## 路线审计矩阵

| 阶段 | 状态 | 证据与缺口 |
|---|---|---|
| PT-1 真实论文基准 | 部分 | `evals/pt9-pt12-final-heldout-gold-20261023.jsonl` SHA-256 `e03aaec49d953664841ab9cf3e17f079829597dc2200e8c071e1d80f9c1b510c`，12 题/6 篇；按路线仍低于 40 题/30 篇。PT5 是 6 题小组。本文冻结 30 个已见来源，0 个 gold 标注；论文数达到路线最低数，人工题数仍未达 40。 |
| PT-2 完整证据检索 | 部分 | 原混合完整证据覆盖仍为7/10。两个遗留题的非盲固定开发回归中，显式双论文 opt-in 策略 Recall@10 为3/4、Recall@20 为4/4；默认结果与冻结轨迹一致。详见 `docs/learning/pt2-two-paper-repair-20261111.md` 和 `evals/pt2-two-paper-balance-20261111.json`。仍需独立真实集复验。 |
| PT-3 可信回答/错误拒答 | 部分 | `evals/pt17-model-e2e-analysis-20261023.json`：4 道可答题完整回答 0；候选证据槽 6/7、筛后 3/7、引用 1/7；不可答有效拒答 0/1。`tests/test_s3.py` 覆盖合成边界，不等于真实论文达标。 |
| PT-4 权限、索引、Web 评测 | 部分 | 已补集合 owner ACL、HTTP/MCP 共用 Principal 授权、直接 SHA 跨 owner 拒绝及 A/B 合成测试；详见 `docs/learning/stage-PT4.md`。仍缺认证中间件生产集成、Web 评测审阅验收和完整多租户安全验证。 |

## PT-1 候选来源目录（30 篇）

本批按 DOI 去重；每篇均为已见开发来源，不构成盲测。来源页、PLOS CC BY 政策页、官方 PDF 下载地址、本地路径和 SHA-256 均登记于 `evals/pt1-candidate-manifest-20261111.json`。本阶段未新增或提交 PDF 文件。

| DOI | 标题 | PDF SHA-256 | 官方文章页 |
|---|---|---|---|
| `10.1371/journal.pcbi.1004961` | Ten Simple Rules for Effective Statistical Practice | `527fc8f7054f80b2a2fd277afb9a1ea7ada2f96659140764729adf12a78d00ad` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1004961>) |
| `10.1371/journal.pcbi.1005412` | Ten simple rules for making research software more robust | `002081be65fbd42c0356d3e49ac7f49fa6202f566f50341481ead22d3cce78b2` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005412>) |
| `10.1371/journal.pcbi.1005510` | Good enough practices in scientific computing | `ed60d4b71c36d650757c7adfe1d52afb5b6b125b7b747f74f79d5ad80e94c017` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005510>) |
| `10.1371/journal.pcbi.1005730` | Ten simple rules for writing a response to reviewers | `7a9dca63168f30698b05742a99f61d5b3b87cf33a01e374b702c8fc22dbfbfbf` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005730>) |
| `10.1371/journal.pcbi.1006141` | Ten quick tips for getting the most scientific value out of numerical data | `030137d7ea8d31c1004976b005d9817f4cefcf686f8ae8acc8472964ec98a816` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1006141>) |
| `10.1371/journal.pcbi.1006561` | Ten simple rules for documenting scientific software | `c2b50ad022577a957672622dec9ae0ad7ab746ef38a04ab051f007814fb76e7d` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1006561>) |
| `10.1371/journal.pcbi.1007007` | Ten simple rules for writing and sharing computational analyses in Jupyter Notebooks | `30af1629e0fe31b51a82c8f01c901a0ecc6d13bb61bc601861aeb3d260397910` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1007007>) |
| `10.1371/journal.pcbi.1007704` | Ten simple rules for innovative dissemination of research | `f608cdf588ac44ef34797a4dac35fa2b4da1800ab038b4ccc3453742d709a452` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1007704>) |
| `10.1371/journal.pcbi.1007846` | Ten simple rules for open human health research | `67cdeb70bbb0697da49ef359b2cce9ac2edd78e5e7b3d294d563e552df61631e` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1007846>) |
| `10.1371/journal.pcbi.1008554` | Ten simple rules for navigating the computational aspect of an interdisciplinary PhD | `af8b3122f5f85e877f423e7cff5fbeb4019593945c9c6ad21de56d03cc6f228e` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1008554>) |
| `10.1371/journal.pcbi.1008879` | Ten simple rules to cultivate transdisciplinary collaboration in data science | `fb6cf1880a44b5c65c9925fc753f36a8032986e01f6ac4a22dd285cf39e1f292` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1008879>) |
| `10.1371/journal.pcbi.1009009` | Ten simple rules for designing analogue science games | `0be11b02dd8e7631d0c1ee7ca41c9ab36c44d8e98289080bb1a9fa45aa4a3344` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1009009>) |
| `10.1371/journal.pcbi.1009757` | Ten simple rules for large-scale data processing | `2f0758d577a8d09dbf45dc0c370ab303a2978858e0e2c0a0b979755c39f308bc` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1009757>) |
| `10.1371/journal.pcbi.1009768` | Ten simple rules for improving research data discovery | `7bc4ddf60ed24be41d5b3337de2a4c1294a8295e1f2ecc798806326c36e3cde8` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1009768>) |
| `10.1371/journal.pcbi.1010033` | Ten simple rules for getting started with statistics in graduate school | `53e867793aa1f3a710004ee3c10346b4c1b8e2e5fdf9abfdf700ec3d3e09cbb1` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1010033>) |
| `10.1371/journal.pcbi.1010164` | Ten simple rules to host an inclusive conference | `98d6d1458eac6b88fc8f8fd8e376ad1707e053f205db2b71e4a35ecdc2f09f4e` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1010164>) |
| `10.1371/journal.pcbi.1010220` | Ten simple rules for leveraging virtual interaction to build higher-level learning into bioinformatics short courses | `ad4f59ea9b8fa6941db4184ea8b648c099ce55c3db57943206b613a90962d30a` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1010220>) |
| `10.1371/journal.pcbi.1010356` | A simple kit to use computational notebooks for more openness, reproducibility, and productivity in research | `3e88c105c0292a07c3dcc32872c6f2acfe865173aebd757dded9874b0ae2dc2a` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1010356>) |
| `10.1371/journal.pcbi.1010362` | Ten simple rules for reporting information on species interactions | `629c33befe0160b0cb463799af659a35fdf49203720f55bd0371bef4d55fe073` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1010362>) |
| `10.1371/journal.pcbi.1010528` | Ten simple rules for creating a global network in computational biology | `22a5065918ae639b88a4bfb58e3b634c98f406340fc199448feacea6c992f1ed` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1010528>) |
| `10.1371/journal.pcbi.1010749` | Ten simple rules for using public biological data for your research | `91f24205d15596227407fc5ade92c71d37c86dd1fc589b8dc1d64d7c7dd38ed0` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1010749>) |
| `10.1371/journal.pcbi.1010879` | Ten (not so) simple rules for clinical trial data-sharing | `950c43a35649934f2375e745c792a599225e0838e9fc1527c3df5829c9b3877f` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1010879>) |
| `10.1371/journal.pcbi.1011698` | Ten simple rules for humane data science | `34466c3a60a651172a015a948148b063e627ab288438d0b4897241d3515dd303` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1011698>) |
| `10.1371/journal.pcbi.1012179` | Ten simple rules to make computable knowledge shareable and reusable | `e887af39e1982b7e164100bf591409340fdbed78153fc11f8a04696518123122` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1012179>) |
| `10.1371/journal.pcbi.1012232` | Ten simple rules for building and maintaining a responsible data science workflow | `f8e2af70e399923198b253109e255d3a818f732ce97dbd5092cf7c6accead567` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1012232>) |
| `10.1371/journal.pcbi.1012402` | Ten quick tips for ensuring machine learning model validity | `176e2321b47a2cf1c726372eafeb24f47b73e9b3d75c91c98545af4dcc5835b5` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1012402>) |
| `10.1371/journal.pcbi.1013657` | Ten simple rules for making biomedical data resources accessible | `fd90106cc19e5a587bf0355822563d1681cf556eaaa92373823d0e84c6a9230e` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1013657>) |
| `10.1371/journal.pcbi.1013970` | Ten simple rules for building a collaborative coding culture | `0b21626f7223a66c7edc4628cd883a568e411067745afc3f055683f4b9643445` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1013970>) |
| `10.1371/journal.pcbi.1014882` | Ten simple rules for responsible use of AI and LLMs in computational biology | `6992aafd1be44a31c70d1dc080691d75eb9cfe50470ad686b65df6143f6b6871` | [PLOS](<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1014882>) |
| `10.1371/journal.pone.0302787` | Workflow for detecting biomedical articles with underlying open and restricted-access datasets | `2aa23da30ca26e61ecff0389045f2f04110f093343b60312144211037b20baa4` | [PLOS](<https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0302787>) |

许可依据：各 PLOS 文章页的版权声明及 [PLOS 官方版权政策](https://journals.plos.org/ploscompbiol/s/licenses-and-copyright)；政策说明 PLOS 文章适用 CC BY 4.0，除非文章另有说明。官方页面逐条链接已入清单。校验器要求 30 个不同 DOI、CC BY 4.0 元数据、有效 PDF 文件头、路径安全和哈希匹配。

PT-1 gold 仍为空，当前 0 题。40 道题及逐页最小完整证据集留作用户人工标注任务；不由模型生成答案或标注。30 篇来源均标为 `development_seen`，不能作为盲测集。

## PT-2/PT-3 与测试边界

本轮未改冻结评测基线。PT-2 完整证据覆盖仍为 7/10；PT-3 真实集完整可答回答仍为 0/4、不可答正确拒答为 0/1。定向回归 `tests/test_s3.py` 与 `tests/test_p13_regressions.py`：41 项通过。

全套测试在受限运行中为 75 项通过、1 项受本机回环权限拦截：`tests/test_local_llm.py::test_local_chat_client_uses_loopback_ollama_json_api`。本地假服务绑定 `127.0.0.1` 的临时端口；连接失败链为 `urllib.error.URLError`，底层 `WinError 10013`（套接字访问被拒），最终 `papertrail/local_llm.py:82` 抛出 `RuntimeError`。该用例获准单独运行后通过；不涉及外网或模型。PT-1 定向测试为 2 项通过。


## 人工标注任务包与 PT-2 离线修复

PT-1 人工任务包见 `docs/learning/pt1-human-annotation-guide-20261111.md` 与 `evals/pt1-human-annotation-task-40-20261111.csv`。40 个问题覆盖30个 DOI；30 个章节事实候选、10 个量化效果边界探测。答案、可答性、题型、最小完整引文、页码、原文摘录、标注者和复核字段全部为空。任务生成不调用模型；校验器、JSONL格式及证据校验、人工规则和虚构格式例已备妥。仍需人工逐题标注与第二人复核；当前 gold 为0题，不能称 PT-1 完成。

PT-2 离线代码缺口：语义检索的 BGE 与去重页路径在 `limit=0` 时可能返回一条，LLM 重排路径也未保证在非正 limit 下不工作。`papertrail/semantic.py` 现统一让 BGE、混合、宽召回、稠密重排、LLM 重排和页去重在 `limit <= 0` 时直接返回空，不触发索引或模型。回归位于 `tests/test_semantic_rerank.py::test_semantic_retrieval_nonpositive_limit_returns_without_work`。PT15 冻结的 `qa.py`、`retrieval.py` 与预登记哈希未改。PT1 任务校验、PT1 来源校验及语义检索定向测试共10项通过；未调用模型。

## PT-2 原始 7/10 失败审计

对 PT9-03、PT9-05、PT12-05 的原始追踪、单路候选与RRF页结果审计见 `docs/learning/pt2-parent-page-diagnostic-20261111.md`。全局子块RRF截断是共性瓶颈。可选父段/页聚合回归命中 PT9-05 一页；PT9-03 与 PT12-05 仍未完整覆盖。历史结果保持 7/10。

