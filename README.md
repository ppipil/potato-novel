# Potato Novel

土豆小说是一个基于 `SecondMe OAuth + Vue 3 + FastAPI` 的互动短篇小说项目。

它当前支持两类主要体验：

- `library` 模式：从书城模板开局，首次访问会先生成全局 seed，后续用户基于 seed 新开一局
- `custom` 模式：输入自定义开头，后端按固定骨架生成一局可游玩的互动故事，并把生成状态以非阻塞方式反馈到书架

项目现在不再只是最初的 OAuth demo。当前后端已经在按 `routes / services / providers / repositories / domain` 分层重构，主链路已经接到新结构上，但仍有少量过渡中的兼容文件。

文档导航见：

- [`docs/README.md`](/Users/pipilu/Documents/Projects/potato-novel/docs/README.md)
- [`docs/architecture.md`](/Users/pipilu/Documents/Projects/potato-novel/docs/architecture.md)

## 当前功能

- SecondMe OAuth 登录与后端签名 session
- 书架页与书城模板列表
- library seed 首访播种、并发保护与复用
- 自定义故事生成与非阻塞等待反馈
- 阅读页 runtime 推进与服务端会话同步
- 故事保存、读取、删除、结局分析
- 自定义故事本地书架缓存、重开与去重
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
2. 再按阅读顺序逐节点补全正文
3. 每个 turn 节点在正文完成后再生成选项

当前链路可能需要数分钟，前端请求超时上限仍按分钟级配置（custom 常用 `300000ms`，library seed 可更长）。  
从 `2026-04` 起，书架页生成交互已改为**非阻塞等待**：用户可继续浏览，生成完成后可从书架提示继续进入结果页。

## 近期体验更新（2026-04）

- 阅读页改为“正文完整展开后再出现选项”，避免最后一段刚出现就被选项区抢走焦点。
- 结局页“保存书架”已改为本地先落库、后台再同步，按钮会显示 `已保存 / 重试同步` 等明确状态，并对同一会话做去重保护。
- 书架里的自定义故事已区分“继续互动”和“重新开始”，同一条自定义故事不会因为反复重开生成多张重复卡片。
- 自定义故事生成链路新增阶段日志与失败分类，便于排查长时间等待、网络异常或节点解析失败。
- 阅读页选项区与模板卡做了密度收敛，减少“组件过大、三选项占满屏”的情况。
- 阅读页新增更稳定的“展开完成后自动滚动到选项区”逻辑，并保留 slide-up 弹出感。
- “局势提示”改为选择前的上下文提示，不再作为历史流持续堆叠。
- 尾声签语请求新增前后端 trace 调试日志，便于排查“长时间等待/未返回”问题。

## 当前状态说明

- 后端 API 主路径已迁移到 `routes/ / services/ / providers/ / repositories/ / domain/`
- [`backend/app/main.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/main.py) 已明显瘦身，但仍保留少量兼容 wrapper 和生成主链
- [`backend/app/model_providers.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/model_providers.py)、[`backend/app/story_prompts.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/story_prompts.py)、[`backend/app/story_text.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/story_text.py) 仍是过渡中的旧文件
- [`backend/app/openings.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/openings.py) 和 [`backend/app/integration.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/integration.py) 也仍属于待继续归位的生成相邻模块

所以当前仓库处在“新结构已落地、旧结构尚未完全收口”的重构中段，而不是最终归档状态。
