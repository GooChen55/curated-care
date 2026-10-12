# 统一接口契约

成功响应为 `{"data":...}`；已处理的业务错误为 `{"detail":"..."}`。用户接口需要 `Authorization: Bearer <token>`。角色由服务端账户决定。

| 方法 | 路径 | 内容 |
|---|---|---|
| POST | /api/auth/login | username、password；返回 token 和用户 |
| POST | /api/auth/logout | 撤销当前会话 |
| GET | /api/me | 当前用户 |
| GET | /api/products、/api/products/{id} | 公共商品查询 |
| GET / PUT | /api/cart、/api/cart/{id} | 查询／设置数量；0 表示移除 |
| POST | /api/orders | address；必需 Idempotency-Key |
| GET | /api/orders、/api/orders/{id} | 本人的订单 |
| POST | /api/orders/{id}/demo-pay | 演示支付，仅演示模式 |
| POST | /api/orders/{id}/cancel | 取消待付款订单 |
| GET | /api/orders/{id}/logistics | 演示物流 |
| POST | /api/orders/{id}/refund-applications | reason；必需 Idempotency-Key |
| POST | /api/assistant/chat | text、request_id、可选 object={type,id} |
| GET | /api/assistant/history | 当前用户最近 100 轮对话 |
| GET | /api/admin/orders、/api/admin/refunds、/api/admin/products | 管理查询 |
| PUT | /api/admin/products/{id} | title/category/description/price/stock/active |
| POST | /api/admin/orders/{id}/ship | 标记发货 |
| POST | /api/admin/refunds/{id}/review | approve、note |
| GET / POST | /api/admin/knowledge | 列表／导入 title、content |
| DELETE | /api/admin/knowledge/{id} | 删除文档和片段 |

助手返回 text、sources、trace、mode、pending。`mode=local` 表示没有启用 LLM；sources 包含文档标题、原文和文档标识。业务写入不接受模型提供的金额或身份。

Python 知识服务内部 `/search`、`/documents` 需要 `X-Service-Token`；助手 `/chat`、`/history` 必須用用户 Bearer token。Python 服务端口不对外发布。
