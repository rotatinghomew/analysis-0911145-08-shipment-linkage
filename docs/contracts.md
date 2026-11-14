# 产品数据与调用约定

nodes 定义有向无环离散机理图。rows 的 when 是完整父节点组合，probabilities 与 states 顺序对应，每个 [lower,upper] 约束一个条件概率且同一行和为一。精确概率用相等上下界。evidence 的 likelihood 为对应状态下的非负似然，不要求其和为一；同一传感来源不得人为复制为独立证据。actions 的 loss_by_damage 顺序对应 damage 状态，单位为每批成本；available_tests.probabilities 的行是真实节点状态、列为补验报告状态，cost 同一成本单位。补验只能使用预算可达项。新接口 POST /evidence-diagnosis 接收 {case, exclude_evidence?, budget?}，返回 {snapshot, posterior, compatibility, test_value, diagnostics}。compatibility 区分图校验错误和联合证据零支持，posterior 的界限明确参数集合含义，test_value 必须基于决策损失而非仅按熵排序。图用于条件推断，未授权自动修改运输或责任认定。

现有 GET /health、GET /cases 和 POST /preview 保留原有资料预览。新增 GET /study-cases 和 POST /study-preview {case} 已可用，只校验与描述 data/study 的资料；推断消费路由尚未实现。app.client.analysis 指向上文约定的新消费接口。所有 snapshot 都是相应原始资料字节的 SHA-256，输出仅使用有限 JSON 数值，无法判断用明确状态与 null 表达，不得返回 NaN。资料只供本地分析，不连接外部服务。

posterior 为按节点名索引的概率界限列表，与该节点 states 顺序一致。compatibility 含 status，值为 compatible 或 incompatible；零支持证据不得给出正常后验。
