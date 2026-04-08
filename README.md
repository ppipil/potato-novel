# Potato Novel

土豆小说是一个基于 `SecondMe OAuth + Vue 3 + FastAPI` 的互动短篇小说项目。

它当前支持两类主要体验：

- `library` 模式：从书城模板开局，首次访问会先生成全局 seed，后续用户基于 seed 新开一局
- `custom` 模式：输入自定义开头，后端按固定骨架生成一局可游玩的互动故事

项目现在不再只是最初的 OAuth demo。当前后端已经在按 `routes / services / providers / repositories / domain` 分层重构，主链路已经接到新结构上，但仍有少量过渡中的兼容文件。

更详细的结构说明见：

- [`docs/architecture.md`](/Users/pipilu/Documents/Projects/potato-novel/docs/architecture.md)

## 当前功能

- SecondMe OAuth 登录与后端签名 session
- 书架页与书城模板列表
- library seed 首访播种、并发保护与复用
- 自定义故事生成
- 阅读页 runtime 推进与服务端会话同步
- 故事保存、读取、删除、结局分析
- MCP 接口与前端静态资源托管

## 技术栈

- 前端：[`frontend/`](/Users/pipilu/Documents/Projects/potato-novel/frontend)
  Vue 3、Vue Router、Vite
- 后端：[`backend/`](/Users/pipilu/Documents/Projects/potato-novel/backend)
  FastAPI、Uvicorn、httpx、psycopg

## 目录概览

- [`frontend/`](/Users/pipilu/Documents/Projects/potato-novel/frontend)：前端应用
- [`backend/app/`](/Users/pipilu/Documents/Projects/potato-novel/backend/app)：后端主代码
- [`backend/scripts/`](/Users/pipilu/Documents/Projects/potato-novel/backend/scripts)：本地调试脚本
- [`openspec/`](/Users/pipilu/Documents/Projects/potato-novel/openspec)：OpenSpec 变更与设计文档
- [`docs/`](/Users/pipilu/Documents/Projects/potato-novel/docs)：项目结构与架构说明

## 本地启动

### 后端

```bash
cd /Users/pipilu/Documents/Projects/potato-novel/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd /Users/pipilu/Documents/Projects/potato-novel/frontend
npm install
cp .env.example .env
npm run dev
```

默认本地入口：

- 前端：`http://localhost:3000`
- 后端：`http://127.0.0.1:8000`

## 关键环境变量

OAuth：

- `SECONDME_CLIENT_ID`
- `SECONDME_CLIENT_SECRET`
- `SECONDME_AUTH_URL`
- `SECONDME_TOKEN_URL`
- `SECONDME_USERINFO_URL`
- `SECONDME_SCOPE`
- `SESSION_SECRET`

故事生成：

- `VOLCENGINE_API_KEY`
- `VOLCENGINE_MODEL`
- `VOLCENGINE_BASE_URL`
- `VOLCENGINE_CHAT_PATH`

可选存储：

- `DATABASE_URL`

## 当前生成链路

当前自定义故事与 library seed 的主生成链路是“两阶段全量生成”：

1. 先构造固定故事骨架
2. 再为 turn 节点生成选项
3. 最后为全部节点生成正文

当前链路可能需要数分钟，前端整次等待上限已经放宽到 `5 分钟`，后端单次 provider 请求超时为 `180 秒`。

## 当前状态说明

- 后端 API 主路径已迁移到 `routes/ / services/ / providers/ / repositories/ / domain/`
- [`backend/app/main.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/main.py) 已明显瘦身，但仍保留少量兼容 wrapper 和生成主链
- [`backend/app/model_providers.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/model_providers.py)、[`backend/app/story_prompts.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/story_prompts.py)、[`backend/app/story_text.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/story_text.py) 仍是过渡中的旧文件

所以当前仓库处在“新结构已落地、旧结构尚未完全收口”的重构中段，而不是最终归档状态。
