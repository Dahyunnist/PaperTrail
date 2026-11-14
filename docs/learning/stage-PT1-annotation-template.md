# PT-1 五题人工标注模板切片

`evals/pt1-annotation-slice-5-20261114.jsonl` 从冻结题单选取 PT1-H001–H005。五题全是候选，不是 gold。PDF 路径、SHA、物理页和证据定位均留为 `pending`；模板不含 PDF 摘录、答案或标注结论。

## 状态机

- `draft`：来源定位未核实、标注未完成或仍有待裁决问题。现有五题都处于此状态。
- `gold`：仅当来源路径/SHA/页码/定位完整、两名不同标注者分别声明独立并填完问题类型/可答性/最小充分证据/支持或冲突关系、所有分歧由人工裁决后，validator 才接受。

validator 只核字段和流程门槛，不核实真实身份、PDF 字节或人工判断正确性。最终入库前仍需现有 PT-1 gold validator 对照来源 SHA、物理页和逐字 span 复核。不得把候选问题或自动结果标为 gold。

## 人工操作

1. 两位标注者分别复制 `evals/pt1-annotation-slice-5-20261114.jsonl` 到各自本机，不共享填写结果。各自核对权威 manifest 中 PDF SHA，再在本机 PDF 核对物理页和最小短引文；填写来源定位，不把长摘录抄入跟踪文件。
2. 每题分别填写 `question_type`、`answerability`、答案或拒答理由、最小充分证据、`support_conflict`、页码/定位、不同的标注者 ID 和 `independent=true`。不要修改候选集文件。
3. 双方完成后由第三人逐题对照原文裁决，记录理由并统一结果。未决冲突保持 `draft`。
4. 人工结果整理到另一份 JSONL，再运行：

   ```powershell
   .\.venv\Scripts\python.exe scripts\validate_pt1_annotation_slice.py .local\pt1-annotation-slice-adjudicated.jsonl
   ```

5. 此 validator 只检查 SHA 格式、正页码、双人独立字段和裁决状态；它不读取 PDF，也不能证明标注真实正确。之后仍须用正式 PT-1 来源校验器验证 SHA、页码和逐字 span。

PT-1 总进度仍 **0/40**。这五题只有经人工完成和来源复核后才可计入人工标注进度；当前模板不能算 gold，也不代表 PT-2 验收完成。
