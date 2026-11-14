# 运行与验证

现有业务预览、资料校验及真实 HTTP 传输由 `python -m unittest discover -s tests -v` 验证；`python -m app.demo` 临时启动服务，通过消费端读取旧业务和新资料的描述输出。固定依赖的安装和容器准备方法见 README。

`RUN_ACCEPTANCE=1 python -m unittest tests.test_acceptance -v` 用于新分析消费接口接通后的基本字段与信息不足契约，当前默认跳过。该测试不是算法正确性的证明，需结合产品约定补充相应的小规模可核对计算、敏感性及信息截止回归。完成后演示应请求真实分析路由，不按资料名返回静态结论；正式展示不安装依赖，资料规模允许在 90 秒内结束。
