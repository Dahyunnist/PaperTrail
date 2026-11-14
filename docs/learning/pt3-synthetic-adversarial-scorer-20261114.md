# PT-3 synthetic adversarial scorer（2026-11-14）

5 个 synthetic case 覆盖完整可答、部分证据、不可答正确拒答、可答题误拒答、无支持 claim。Scorer 用题目 `abstain` 区分 `correct_abstention`、`false_refusal`、`false_answer`；拒绝 claim 记录为 `unsupported_claim`。引文校验要求 SHA、物理页和 quote 同时匹配。

定向组 9 passed。Windows pytest 临时目录含 `#!` 等 URI 保留字符；修正 SQLite 只读连接用 `Path.as_uri()` 编码路径。该组仅测 synthetic fixture 契约，不是模型质量或真实论文指标。PT-1 仍 0/40，真实 PT-2/PT-3 验收等待双人标注与来源复核。
