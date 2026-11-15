# PT-2/PT-3 确定性评测审计（2026-11-15）

## 本次确认

- 仅用测试临时目录内生成的合成 PDF、合成索引、合成 gold 和合成来源清单。
- 未读取私人 PDF、正式 gold/holdout 内容或既有临时目录；未调用模型。
- 报告含项目、Git SHA、dataset ID 与 SHA-256、split、模型标识、prompt/tool/runtime 哈希、scorer SHA、gold 来源、成本、run/trace/span ID、预算、时间、状态、报告指纹、输入清单与 gold 的独立哈希。
- `dataset_sha256` 是来源清单 SHA 与 gold SHA 的组合绑定；两个原始 SHA 仍分别保留。
- 模型未运行时，模型 ID 为 `none`、成本为 0；模型专属哈希为 null，并在共享清单标为 `not_applicable`。
- 缺失 gold 来源保留 null，共享清单标为 `not_recorded`，不填造来源名称。
- 成功状态为 `passed`。比较阶段异常会写 `failed` 报告，只记录失败阶段和异常类型；不写异常消息。
- trace 事件使用与报告一致的 run/trace ID，各事件有独立 span ID。事件属性按名称白名单限制。
- 报告不复制来源清单中的自由文本 `limits`。合成哨兵检查确认问题、答案、限制文本和异常消息不进入报告或 trace。

## 离线验证

成功和失败评测均由本地合成夹具驱动。测试校验输入 SHA、组合 dataset SHA、共享清单投影、失败字段、trace 关联和隐私哨兵。

## 未覆盖边界

- 来源清单/gold 哈希校验、解析或预检失败发生在比较阶段前；这些错误仍抛出异常，不生成失败报告。
- 本轮未运行 PT-17 或任何读取正式 gold/holdout 的测试。
- 未验证任何模型运行、真实论文数据、人工评分或线上追踪后端。
- `runtime_digest` 对无模型流程不适用；报告另记录 Python、平台和耗时，不代表锁文件环境哈希。
