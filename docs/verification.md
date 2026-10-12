# 验收记录

日期：2026-10-12。验收环境为本地演示模式，未使用真实支付、物流或真实模型 API。

| 检查 | 结果 |
|---|---|
| Java `mvn verify` | 4 项通过，覆盖订单幂等、归属、取消和退款库存、退款状态限制 |
| Python 单元与模型适配 | 6 项通过，覆盖状态往返、安全条件、资料来源、文档更新/删除、模型白名单与证据传递 |
| 真实 HTTP 联调 | 3 项通过，覆盖认证/越权、下单/确认退款/恢复/审核、并发库存与知识管理 |
| Vue 生产构建 | 通过，包名 curated-care-storefront |
| Python 语法检查 | 两个服务包通过 compileall |
| 运行入口 | CommerceApplication、curated_assistant.api:app、curated_knowledge.api:app 正常 |
| 服务健康 | Java、助手、知识库、前端均 ready |
| Docker Compose 配置 | config --quiet 通过 |

业务测试使用专用测试商品，结束时下架并保留演示订单与审计。既有业务数据库、会话存储和用户自建文档沿用当前数据文件。

模型接口测试使用模拟响应，不代表真实模型回答质量或可用性。当前 Docker 引擎未运行，本次未重新构建和启动容器；需在引擎启动后执行 `docker compose up -d --build` 验证镜像和容器。

支付、物流、资金退款为演示流程；真实渠道、外部检索与真实模型需单独配置和验收。具体边界见 [产品范围](product.md)。
