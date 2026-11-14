# 产品数据与调用约定

orders 的 slots 为允许匹配回单份数，receipts 的 units_consumed 可大于一。candidates 中 score 是未校准相似度，features 为比对特征；无边不表示业务确认排除。reviews 按 revision 顺序记录 accept/reject，硬约束冲突需显式报告。ground_truth 仅在训练分区存在，不能用于评价分区归属。POST /resolve {case, reviews?} 返回 {snapshot, matches, unmatched, metrics, review_queue, diagnostics}。matches 不得超过任何一侧容量；metrics 按商户报告准时率/补偿判断及不确定性含义，未匹配件必须留在适用分母说明中。

当前 GET /cases、POST /preview 和 GET /health 已可用；client.analysis 是待接入的业务消费调用，新分析路由尚不存在。原始数据通过 app.store 读取，snapshot 为输入字节的 SHA-256。新增接口须保留现有预览能力和 JSON 有限数值约定。

matches 是含 order、receipt 的记录列表；reviews 若与已有硬判断冲突，返回空 matches 与可定位冲突的 diagnostics，不生成貌似干净的新归属。receipt 的 parcel_capacity 是可消费次数，units_consumed 是消耗订单 slots 的份数。
