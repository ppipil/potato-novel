# 项目结构与当前架构

这份文档用于说明 Potato Novel 当前的真实结构、主要功能链路，以及后端分层重构目前进行到哪一步。

它的目标不是替代 OpenSpec 设计文档，而是给新线程、未来维护者和自己快速建立项目心智模型。

## 项目是什么

Potato Novel 是一个互动短篇小说项目，围绕以下两条核心体验构建：

- `library` 模式：用户从书城模板开局，后端先维护全局 seed，再基于 seed 为用户创建个人 session
- `custom` 模式：用户输入自己的故事开头，后端按固定骨架生成一局完整可玩的互动故事，并把生成中的状态反馈回书架

系统同时包含：

- SecondMe OAuth 登录
- 故事生成与阅读 runtime
- 已保存故事与结局分析
- MCP 接口

## 顶层目录

- [`frontend/`](/Users/pipilu/Documents/Projects/potato-novel/frontend)
  Vue 3 前端应用，承接书架、阅读页、OAuth 回调和故事保存流程。
- [`backend/`](/Users/pipilu/Documents/Projects/potato-novel/backend)
  FastAPI 后端，负责 OAuth、故事生成、session、seed、存储访问和 MCP。
- [`openspec/`](/Users/pipilu/Documents/Projects/potato-novel/openspec)
  结构重构与演进的规格文档。
- [`docs/`](/Users/pipilu/Documents/Projects/potato-novel/docs)
  当前项目说明与架构文档。

## 后端当前结构

当前 [`backend/app/`](/Users/pipilu/Documents/Projects/potato-novel/backend/app) 已经演进出新的分层：

- [`backend/app/routes/`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/routes)
  HTTP 路由层。负责请求解析、调用依赖、返回响应。
- [`backend/app/services/`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/services)
  业务编排层。负责 generation、runtime、session、library seed 等流程。
- [`backend/app/providers/`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/providers)
  外部模型边界。负责 provider transport、prompt、模型输出解析。
- [`backend/app/repositories/`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/repositories)
  持久化访问层。统一 stories / sessions 的 JSON / DB 读写。
- [`backend/app/domain/`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/domain)
  纯规则与数据结构层。负责 story package 规则、session 模型标准化等。

### 当前主要文件

- [`backend/app/main.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/main.py)
  应用初始化、middleware、依赖装配，以及少量尚未完全迁走的兼容 wrapper 与生成主链入口。
- [`backend/app/routes/auth.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/routes/auth.py)
  OAuth 登录、exchange、me、logout。
- [`backend/app/routes/library.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/routes/library.py)
  书城模板列表、显式播种、基于 seed 开局。
- [`backend/app/routes/sessions.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/routes/sessions.py)
  统一开局、自定义生成、结局分析。
- [`backend/app/routes/stories.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/routes/stories.py)
  已保存故事的增删查改。
- [`backend/app/routes/mcp.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/routes/mcp.py)
  MCP 统一入口。

## 服务层职责

- [`backend/app/services/story_generation_service.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/services/story_generation_service.py)
  两阶段生成主编排。当前顺序是：
  骨架 -> 按阅读顺序逐节点正文 -> 当前节点选项
- [`backend/app/services/story_runtime_service.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/services/story_runtime_service.py)
  runtime 初始化、可复用包判断、story package 编译。
- [`backend/app/services/library_seed_service.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/services/library_seed_service.py)
  library seed 的查找、并发锁、生成中占位、等待、失败回滚、最终落库。
- [`backend/app/services/story_session_service.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/services/story_session_service.py)
  开局分流、自定义生成入参与结局分析上下文整理。

## Provider / Domain / Repository 的边界

### Providers

- [`backend/app/providers/secondme.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/providers/secondme.py)
- [`backend/app/providers/volcengine.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/providers/volcengine.py)
- [`backend/app/providers/prompts.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/providers/prompts.py)
- [`backend/app/providers/parsers.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/providers/parsers.py)

这里负责“外部模型相关”的事情，包括：

- 发请求
- 组 prompt
- 把模型输出解析成内部结构

### Domain

- [`backend/app/domain/session_models.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/domain/session_models.py)
- [`backend/app/domain/story_package.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/domain/story_package.py)

这里负责“模型无关、存储无关、HTTP 无关”的规则，例如：

- `sourceType` 规范化
- session 序列化
- story package 的选择风格、effects、finalize、validation、模板骨架

### Repositories

- [`backend/app/repositories/stories_repo.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/repositories/stories_repo.py)
- [`backend/app/repositories/sessions_repo.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/repositories/sessions_repo.py)

这里统一承接：

- JSON 文件模式
- Postgres 模式
- 记录查询、保存、upsert、删除

## 当前生成顺序

当前 story package 生成不是“一次返回整包”，而是两阶段全量生成：

1. 固定骨架
2. 按阅读顺序为节点补正文
3. 仅在 turn 节点正文完成后生成该节点选项

这意味着当前系统更偏向“结构稳定优先”，而不是“单次大模型自由生成”。
同时，阅读页的展示节奏也已经对齐为“正文完整 reveal 后再出现选项”。

## 当前书架与保存行为

当前书架页除了模板开局，还承接以下自定义故事行为：

- 自定义故事生成采用非阻塞等待，用户可继续停留在书架浏览其他内容。
- 自定义故事在本地缓存中按稳定条目标识去重，不会因为重复进入或重新开始生成多张相同卡片。
- 已完成的自定义故事再次进入时会执行“重新开始”，未完成的则继续原局互动。
- 书架里的自定义故事支持删除动作，本地缓存会在读取时自动清理旧重复项。

当前结局保存行为：

- 前端点击“保存书架”后会先写入本地书架，再尝试后台同步。
- 同一完成会话在前后端都做了去重保护，避免重复保存生成多个条目。
- 保存按钮会根据状态显示 `已保存`、`重试同步` 等明确反馈，而不是回退到初始态。

## 当前 timeout 设置

为了适应多次串行节点生成，当前超时设置为：

- 前端整次自定义生成等待：`300000ms`
- 后端单次 provider 请求：`180s`

如果未来链路继续变长，更推荐改成任务式异步生成，而不是继续线性提高超时。

## 当前仍处于过渡态的部分

虽然新分层已经建起来，但后端还没有完全收口到最终形态。

当前仍保留的过渡文件有：

- [`backend/app/model_providers.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/model_providers.py)
- [`backend/app/story_prompts.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/story_prompts.py)
- [`backend/app/story_text.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/story_text.py)
- [`backend/app/openings.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/openings.py)
- [`backend/app/integration.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/integration.py)

这些文件仍在被新结构复用，说明项目当前是“重构中段”，不是“旧结构已彻底移除”的最终状态。

另外 [`backend/app/main.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/main.py) 已经明显瘦身，但仍比理想状态厚，里面还保留：

- 一些兼容 wrapper
- 节点生成主链
- 少量状态推进与 session payload 组装

## 建议的后续收尾方向

如果继续做结构收口，优先级建议是：

1. 继续瘦 [`backend/app/main.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/main.py)
2. 把旧的 [`backend/app/model_providers.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/model_providers.py)、[`backend/app/story_prompts.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/story_prompts.py)、[`backend/app/story_text.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/story_text.py) 收口或降成非常薄的兼容层
3. 再补一轮关键链路回归验证，确认 library/custom 两条路径都稳定

## 哪些文档是最新的

- 文档导航：[`docs/README.md`](/Users/pipilu/Documents/Projects/potato-novel/docs/README.md)
- 入口说明：[`README.md`](/Users/pipilu/Documents/Projects/potato-novel/README.md)
- 当前结构说明：[`docs/architecture.md`](/Users/pipilu/Documents/Projects/potato-novel/docs/architecture.md)
- 当前接口与流程：[`docs/architecture/current-api-and-flows.md`](/Users/pipilu/Documents/Projects/potato-novel/docs/architecture/current-api-and-flows.md)
- SecondMe 接入：[`docs/integrations/secondme.md`](/Users/pipilu/Documents/Projects/potato-novel/docs/integrations/secondme.md)
- 历史方案归档：[`docs/archive/legacy/`](/Users/pipilu/Documents/Projects/potato-novel/docs/archive/legacy)
- 重构规格与设计：[`openspec/changes/refactor-backend-architecture-and-docs`](/Users/pipilu/Documents/Projects/potato-novel/openspec/changes/refactor-backend-architecture-and-docs)
