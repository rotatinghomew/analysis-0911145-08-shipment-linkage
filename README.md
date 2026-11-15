# 共享观测与区间条件概率下的货损证据更新及补验价值

本地分析工作台保留已有业务资料与预览能力，并在 `data/study` 的合成机理图上提供条件推断：在到货坏果争议中同时看温度记录与到货外观，给出针对当前证据的联合判断、知识不确定性区间、矛盾证据定位，以及补验的决策价值。

数据均为本地合成，不含真实姓名、电话号码或生产系统凭据。`standard` 是常规资料，`interval` 含区间条件概率与多项候选补验，`single` 是无证据的单节点先例，`edge` 用于检查证据互相矛盾。它们只描述观测与机理假设，不预设分析结论，也不构成责任认定。

## 能回答什么

- **联合判断，而不是两张选票**：证据在机理图上按节点条件相乘。温度记录和到货外观都由同一段受热影响时，它们通过共同原因相关，不会被当成独立观测重复计权。
- **知识不确定性**：条件概率只有区间时，后验给出可行参数集合上的逐状态界限（`posterior`），并明确这些界限不保证由同一参数完成同时达到。
- **矛盾定位**：若联合证据没有任何正支持状态，返回 `compatible/incompatible` 中的 `incompatible`、`reason=zero_support`，列出最小复核证据组，`posterior` 为 `null`，不会把概率重新归一成一个看似正常的结论；图本身非法则通过 `reason=graph_invalid` 区分。
- **撤除一项观测**：`exclude_evidence` 给出撤除前后的后验差异与决策是否改变，用于解释结论为什么变。
- **补验价值**：`test_value` 按“决策损失下降 − 补验成本”比较预算内补验，并剔除超预算项；排序与推荐都基于决策损失，不按熵排序，也不把多项补验当作独立增益相加。
- **可追溯**：响应保留资料 `snapshot`（SHA-256）、`graph_version`、证据来源及其 included/excluded 状态、决策依据与解释限制。

观察到某个原因更可能只是条件推断的结果，不等于证明谁造成了损失，也不能解读为干预效果或责任认定。

## 本地使用

Python 3.11，依赖版本固定在 `requirements.txt`。NumPy/SciPy 是分析工作台的数值工具；当前推断实现以标准库完成精确枚举，预览逻辑同样主要使用标准库。准备阶段安装依赖，仓库不在启动或测试时下载任何资源。

支持 Python 3.11 系列的补丁版本；Docker 基础镜像通过 SHA256 固定为 Python 3.11.14，依赖清单保持精确版本。相同依赖还需在非 root 的 Python 3.11.2 Linux 环境中验证，应用不依赖特定补丁版本。

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m app.demo
python -m app.server
```

服务监听 `127.0.0.1:8080`，也可通过 `PORT` 调整。预览与分析请求由 `app/client.py` 发起；`app.demo` 在临时端口启动真实服务，通过真实 HTTP 消费调用完整打印旧业务预览、资料描述输出、每个分析资料的诊断结果、一次撤除证据的敏感性对照，以及一次收紧预算后的补验清单；不是录制日志的回放。服务接口和数据文件的可见性约定不能互相替代。

接口与字段约定见 `docs/contracts.md`，验证方法与算法核对见 `docs/verification.md`。

## 可复现环境

```sh
docker build -t local/shipment-linkage:baseline .
docker run --rm --network none local/shipment-linkage:baseline python -m unittest discover -s tests -v
docker run --rm --network none local/shipment-linkage:baseline
```

准备阶段允许构建镜像和预装依赖；正式演示不进行构建或安装。小样本演示在 90 秒内结束。验收测试默认启用，可用 `RUN_ACCEPTANCE=0` 在受限环境中跳过：`python -m unittest tests.test_acceptance -v`。
