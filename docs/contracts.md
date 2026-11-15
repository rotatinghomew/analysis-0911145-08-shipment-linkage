# 产品数据与调用约定

nodes 定义有向无环离散机理图。rows 的 when 是完整父节点组合，probabilities 与 states 顺序对应，每个 [lower,upper] 约束一个条件概率且同一行和为一。精确概率用相等上下界。evidence 的 likelihood 为对应状态下的非负似然，不要求其和为一；可选 `source` 标明传感来源，同一 `source` 不得出现两次（重复即视为把同一观测拆成独立证据）。actions 的 loss_by_damage 顺序对应 damage 状态，单位为每批成本；available_tests.probabilities 的行是真实节点状态、列为补验报告状态，可选 `report_states` 为报告状态命名，cost 同一成本单位。补验只能使用预算可达项。

## POST /evidence-diagnosis

请求 `{case, exclude_evidence?, budget?}`：

- `case` 是 data/study 中的资料名，不接受路径。
- `exclude_evidence` 是要撤除的证据标识列表，用于敏感性对照；未知标识返回 400。
- `budget` 覆盖资料中的补验预算，必须是非负有限数值；预算按单项补验成本检查。

响应：

```
{snapshot, posterior, compatibility, test_value, diagnostics}
```

- `snapshot` 是原始资料字节的 SHA-256；`diagnostics.graph_version` 保留图版本。
- `posterior` 为按节点名索引的概率界限列表 `[[lower,upper], ...]`，与该节点 states 顺序一致。界限是**可行条件概率完成集合上的逐状态极值**：不同节点的界限不保证由同一个参数完成同时达到，同一节点的各状态界限也不保证相加为一。条件概率行之间按独立多面体处理。
- `compatibility.status` 为 `compatible` 或 `incompatible`，`reason` 区分 `graph_invalid`（结构或参数非法、规模超限）与 `zero_support`（联合证据在可行参数与状态上无正支持）。零支持时 `posterior` 与 `test_value` 为 `null`，`compatibility.review_evidence` 与 `diagnostics.conflicts` 给出需要复核的最小证据组；不会把概率重新归一成一个看似正常的结论。
- `test_value` 以决策损失为基础：对每个可行完成，取本次分析建议的处置在该完成下的期望损失，减去等待补验结果后再选最优处置的期望损失，再减去补验成本，得到净价值区间。排序使用区间下端，`recommended_test` 只在预算内且该下端为正时给出。该下端是枚举出的顶点完成上的最小值，不是对全部可行参数的下界证明；多项补验的相关性与组合成本未建模，不把单项价值相加。
- `diagnostics` 保留证据来源（含 `included` / `excluded` 状态）、参数不确定性的表示与计算方法、决策依据、撤除证据前后的对照，以及解释限制。

处置决策采用最坏情形期望损失最小（`minimax_expected_loss_over_feasible_cpt_completions`），这是成本决策规则，不是责任或因果效应判断。

输出仅使用有限 JSON 数值，不得返回 NaN。资料只供本地分析，不连接外部服务。

## 推断口径

证据似然按图节点条件相乘（同一节点上的多条证据先按状态相乘）。共享上游原因会让下游观测相关，因此温度记录与到货外观不是两张独立选票；接口在诊断中明确说明这一点，并对同一节点多条证据给出警告。

某个原因在观测后更可能，只是条件推断的结果，不等于证明它造成了损失，也不能解读为干预效果或责任认定。

## 其他路由

GET /health、GET /cases、POST /preview 保留原有资料预览；GET /study-cases、POST /study-preview {case} 只校验与描述 data/study 的资料；POST /evidence-diagnosis 之外的未知路由返回 404（`/study-cases` 仍只列资料名）。app.client.analysis 指向新的消费接口。
