# 阶段 P12：让默认 BM25 与向量依赖解耦

日期：2026-10-20

## 发现

PaperTrail 默认检索模式是 BM25，但 `retrieval.py` 在模块导入时就加载 `numpy`、`joblib` 和 `scikit-learn`。问答与 MCP 服务会导入这个模块，所以仅使用关键词检索也会被可选向量依赖阻塞。向量模式依赖未安装时，错误也会在应用启动阶段出现，无法指出缺少哪个组件。

## 修复

- 将向量索引和检索依赖延迟到向量函数调用时导入。
- BM25 问答、检索模块导入不再需要 `joblib` 或 `scikit-learn`。
- 空向量查询直接返回空列表。
- 真正调用向量功能但缺少依赖时，返回指向 `requirements-dev.txt` 的明确错误。
- BGE 模块只在 BGE 模式加载；`joblib` 也只在读写 BGE 索引时导入。

## 验证

新增隔离子进程测试，拦截 `joblib`、`numpy` 和 `sklearn` 导入，验证 BM25 路径可用、空向量查询可结束、向量功能给出依赖提示。另运行 QA、语义重排、黄金集、审计、本机模型适配器和 MCP 测试。

- 结果：37 项通过。
- 另有 1 项向量索引集成测试因当前测试环境没有 `scikit-learn` 而未运行；该测试必须在安装 `requirements-dev.txt` 后验证。
- 测试环境使用 Python 3.11、仓库本机 PyMuPDF 与 Flask 运行依赖。
- 没有读取或上传本机论文语料，也没有调用模型 API。

完整环境中的复现命令：

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

当前无 scikit-learn 环境复现可运行测试：

```powershell
python -m pytest -q -k "not s1_indexes_text_pages_notes_versions_and_exact_duplicates"
```

## 边界

这次解决默认 BM25 启动依赖问题，不提高召回率，也不改变 P11 报告里的文献问答成绩。向量检索仍需在已安装完整开发依赖的环境中单独验收；P11 的页命中和生成主张拒绝问题仍需独立修复与盲测。
