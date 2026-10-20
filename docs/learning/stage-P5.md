# P5 学习记录：可审计轨迹与人工 reward

## 记录字段

每轮 QA 持久化候选 chunk 的 SHA、页码、分数和检索信号；通过原 PDF 校验的证据页与摘录 SHA；模式、上下文 query、回答状态、总耗时、本机模型名、服务返回 token/时长计数；生成 claim 数、被支持审查拒绝的数量；人工评分、理由和 reward。轨迹不写入源文件绝对路径。

Ollama 若返回 `prompt_eval_count`、`eval_count`、`total_duration`，系统累计生成与审查两次调用的计数。非生成模式、无 usage 字段时记录 null 或零值，不估算 tokens 或货币成本。

## 人工评分与 reward

可给每轮标记 `correct`、`partially_correct`、`incorrect`、`abstention_correct` 或 `abstention_wrong`。基础分依次为 1、0.5、-1、0.5、-0.5。再乘 claim grounding ratio（1 减拒绝 claim 比例），扣除 `min(latency_ms / 60000, 0.1)`。系统保存 reward 分量与公式，方便以后替换或做消融。

该分数是可解释的监督信号，不是客观真值。`correct` 等标签由人工在读过来源后录入；模型支持性审查仅贡献 grounding 惩罚。当前没有评分样本、用户任务完成率统计或足够轨迹，不训练 RL 或声称 Agentic-RL 收益。货币成本也不估算；本机推理的能源成本未计量。

## 导出和验证

```powershell
python -m papertrail trajectory-rate --db .local/papertrail.sqlite3 --turn-id <turn-id> --rating correct
python -m papertrail trajectory-export --db .local/papertrail.sqlite3 --out .local/trajectories.jsonl
python -m pytest tests/test_reward.py -q
python -m pytest -q
```

轨迹只在用户显式运行导出命令时写 JSONL。全量测试包含评分、公式分量、路径隔离和 JSONL 往返用例。

## 经验

Agentic-RL 起点是可复现的任务轨迹和人类结果标签，不是先训练。检索日志可定位失败阶段；引用 hash 可重放证据核验；单独记录 latency 和 token 数可量化成本。先积累独立人工标注，再讨论训练和 held-out 对照。
