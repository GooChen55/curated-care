# 运行与排查

从项目根目录运行 `python scripts/manage.py status`。默认访问地址是 `http://127.0.0.1:5273`，可以直接在 Chrome 打开，无需安装 Tabbit。

## 日常开发

前端运行在 Vite 开发服务器中，Vue/CSS 修改会自动更新。修改 Java 后执行 `mvn -f services/commerce/pom.xml verify`；运行包独立复制到 `.runtime/`，允许服务运行时构建。要启用新的 Java/Python 代码或环境变量，执行 `python scripts/manage.py stop`，再执行 `python scripts/manage.py start`。

三个服务各有一个运行入口：Java 的 `CommerceApplication`、助手的 `curated_assistant.api:app`、知识库的 `curated_knowledge.api:app`。

## 健康与日志

| 服务 | 健康地址 | 日志 |
|---|---|---|
| 业务服务 | `http://127.0.0.1:19081/api/health` | `.runtime/commerce.log` |
| 助手 | `http://127.0.0.1:19082/health` | `.runtime/assistant.log` |
| 知识库 | `http://127.0.0.1:19083/health` | `.runtime/knowledge.log` |
| 统一页面 | `http://127.0.0.1:5273` | `.runtime/storefront.log` |

健康接口表示进程可访问，不等于真实模型或高级中间件均可用。若只有页面正常而聊天失败，先检查助手、知识库，再检查 Java 日志中的代理错误。

启动脚本发现端口占用会停止启动，避免覆盖其他应用。存在进程记录时先检查 status；不要直接删除记录或按通用 `java`/`python` 进程名强行结束进程。

## 持久化与备份

业务数据位于 `data/commerce.mv.db`，助手状态与历史位于 `data/assistant.sqlite3`，知识文档位于 `data/knowledge.sqlite3`。备份前停止本项目服务，再复制这些文件和自建知识资料。默认示例数据不是生产业务数据。

Docker 使用独立数据卷，与上述本地数据库不同。`docker compose down` 不删除数据卷；需要保留演示数据时不要使用 `down -v`。

## 模型配置

根目录 `.env` 由启动脚本读取，`private/` 仅用于本机备份配置，不自动注入运行服务。填写 `.env.example` 中的 LLM/Embedding 变量后重启。API 地址应为兼容 API 的版本根路径，例如以 `/v1` 结尾，运行层会追加 `/chat/completions` 或 `/embeddings`。

未配置模型时返回资料摘录。知识文档和相关问题会随启用后的模型请求发送给所配置的服务，请使用适合项目资料的服务和演示内容。

## Windows 中文路径下构建 Docker

若 BuildKit 报共享键 header 非 ASCII，可仅为当前终端设置：

```powershell
$env:DOCKER_BUILDKIT='0'
$env:COMPOSE_BAKE='false'
docker compose build
docker compose up -d --no-build
```

首次拉取镜像和 Maven/Python/npm 依赖需要网络。出现依赖下载失败时先检查错误中的仓库地址，重试同一构建即可复用已下载的镜像层。
