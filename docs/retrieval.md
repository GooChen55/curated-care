# 知识检索

入口为 `services/knowledge/curated_knowledge`。知识服务独立保存文档和片段，管理员经 Java 网关管理资料，助手用服务令牌执行检索。

文档按段落切片，保留标题路径，长段落使用重叠窗口。默认对中文双字和英文词使用 BM25 召回。返回内容包括文档标识、标题、片段原文与分数。

配置 `EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`、`EMBEDDING_MODEL` 后，导入时保存稠密向量，查询时将 BM25 与余弦相似度结果通过 RRF 融合。新增配置或切换模型后重新导入现有文档。

未启用 LLM 时，助手返回资料摘录。启用后，将问题和召回资料传给兼容模型，返回答案及引用。未召回资料时明确说明缺乏依据。

## 外部检索契约

设置 `ADVANCED_KNOWLEDGE_URL` 可将 `/search` 转发给另行部署的检索服务。该服务需接受 `POST /search`，请求包含 `query` 和 `limit`，并校验 `X-Service-Token`。

响应为 `{"data": [...]}`，每个片段包括 `id`、`document_id`、`title`、`content`、`score`。外部服务自行负责数据同步、导入、模型和中间件；统一页面导入的文档默认保存在本地知识库。

真实模型和外部检索服务需单独验证：召回质量、引用一致性、拒答、超时、故障回退与资料更新。
