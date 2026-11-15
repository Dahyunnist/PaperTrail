# PT-1～PT-4 阶段核对矩阵（2026-11-15）

PT-1 按用户要求保持暂停。核对限于代码、历史学习记录和合成离线回归；未读私人 PDF、未读取或修改真实 gold、未调用模型。

| 阶段 | 本轮证据 | 数据来源、样本量 | 结论与局限 | 下一具体缺口 |
|---|---|---|---|---|
| PT-1 | 无新工作 | 冻结任务仍为 40 题，双人标注进度 0/40 | 保持暂停；不生成 gold | 用户解冻后由两位标注者独立标注并仲裁 |
| PT-2 | 冻结 runner 两次重建输出一致；定向测试 3 passed | runner 内 3 个 synthetic query、3 份临时 PDF；BM25、字符 TF-IDF + SVD、RRF 共 9 组；9/9 合成最小证据集合完整 | 可重跑性已证明，不是语料质量指标；dense 不是神经 embedding | 真实独立完整证据覆盖验收依赖 PT-1 双标集 |
| PT-3 | PT-2/3 综合定向组 22 passed，含引用、拒答、部分覆盖、分类和冻结检索回归；另有 8 项安全组包含页码布尔负例 | 临时合成 PDF、冻结 synthetic adversarial 5 类、stub generator 和纯分类输入；无真实答题样本 | SHA/页/span、来源映射、部分覆盖、错误空拒答和 budget-block 分类有离线证据；无本轮质量率。跨来源映射不等于语义冲突判定 | 经人工复核的冲突题和独立答案质量验收；需 PT-1 解冻 |
| PT-4 | 检索前 ACL、版本/删除、API/Web/MCP/direct resource、上传/job owner 定向组共 43 passed | 临时 SQLite、合成 PDF、合成 Principal；本地 SQLite/测试客户端 | 本地应用 ACL 跨路径负例成立；没有生产身份集成或多租户安全证明 | 目标认证中间件与实际 MCP transport 的可信身份联测 |

PT-2 详见 [冻结合成复跑记录](pt2-frozen-synthetic-rerun-audit-20261115.md)，PT-3 详见 [安全边界记录](pt3-synthetic-safety-crosscheck-20261115.md)，PT-4 详见 [多入口 ACL 记录](pt4-cross-entry-acl-audit-20261115.md)。页码类型修复在提交 `7fb5459`。

历史真实/公开开发集数字仍以各自旧报告为准，不并入本轮指标，也不据旧模型结果推断当前质量。本轮没有接触这些数据集。
