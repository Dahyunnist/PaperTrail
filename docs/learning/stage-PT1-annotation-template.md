# PT-1 五题人工标注模板切片

`evals/pt1-annotation-slice-5-20261114.jsonl` 从冻结题单选取 PT1-H001–H005。五题全是候选，不是 gold。PDF 路径、SHA、物理页和证据定位均留为 `pending`；模板不含 PDF 摘录、答案或标注结论。

## 状态机

- `draft`：来源定位未核实、标注未完成或仍有待裁决问题。现有五题都处于此状态。
- `gold`：仅当来源路径/SHA/页码/定位完整、两名不同标注者分别声明独立并填完问题类型/可答性/最小充分证据/支持或冲突关系、所有分歧由人工裁决后，validator 才接受。

validator 只核字段和流程门槛，不核实真实身份、PDF 字节或人工判断正确性。最终入库前仍需现有 PT-1 gold validator 对照来源 SHA、物理页和逐字 span 复核。不得把候选问题或自动结果标为 gold。

## 人工操作

两位标注者各自填写一份副本，不互看答案。每题分别记录 `question_type`、`answerability`、`expected_answer`、最小证据集合、`support_conflict`、证据页与定位、标注者 ID 和独立声明。第三人裁决分歧并填 `adjudication=resolved`；之后才可设 `status=gold`。PT-1 总进度仍 **0/40**，这五题不会自动计入完成数。
