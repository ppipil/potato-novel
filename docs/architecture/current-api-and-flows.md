# 当前真实 API 与流程（代码对齐）

本文档只记录当前代码中仍在使用的接口与主流程，作为维护基线。

## 1. 认证（SecondMe OAuth）

后端认证路由：[`backend/app/routes/auth.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/routes/auth.py)

- `GET /api/auth/login`
  - 跳转至 SecondMe OAuth 授权页，并写入 `oauth_state` cookie。
- `POST /api/auth/exchange`
  - 前端回调页拿到 `code/state` 后调用该接口，后端完成 token 交换并签发会话。
- `GET /api/me`
  - 查询当前登录态。
- `POST /api/auth/logout`
  - 清理会话 cookie。

说明：当前实现并没有 `GET /api/auth/callback` 后端回调接口。

## 2. 书架与模板故事

后端路由：[`backend/app/routes/library.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/routes/library.py)

- `GET /api/library-stories`
- `POST /api/library-stories/{story_id}/generate-seed`
- `POST /api/library-stories/{story_id}/start-from-seed`
- `POST /api/library-stories/{story_id}/start`
- `POST /api/library-stories/import-package`
- `POST /api/library-workbench/ai-complete-node`
- `DELETE /api/library-stories/{story_id}/imported`

## 3. 会话与故事生成

后端路由：[`backend/app/routes/sessions.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/routes/sessions.py)

- `POST /api/story/start`
- `POST /api/custom-stories/generate`
- `POST /api/story/preload`
- `POST /api/story/regenerate`
- `POST /api/story/analyze-ending`
- `POST /api/story/generate`
- `POST /api/story-packages/import`

当前自定义故事生成行为补充：

- 请求负载除 opening 外，还支持额外的补充说明字段，用于辅助约束故事风格、氛围或走向。
- 生成链路采用非阻塞等待，前端可以在等待期间继续停留在书架。
- 后端会输出生成阶段日志与路由失败日志，便于排查长时间等待、节点解析失败或 provider 异常。

## 4. 已保存故事

后端路由：[`backend/app/routes/stories.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/routes/stories.py)

- `POST /api/story/save`
- `GET /api/stories`
- `GET /api/stories/{story_id}`
- `DELETE /api/stories/{story_id}`
- `POST /api/stories/{story_id}/ending-analysis`

当前保存行为补充：

- 结局页点击“保存书架”后会先进行本地保存，再尝试后台同步。
- 同一完成会话会按 `sessionId` 做去重保护，避免重复保存产生多个条目。
- 自定义故事书架卡片在本地缓存里也会按稳定条目标识去重，并支持已完成故事重新开始。

## 5. MCP 与系统接口

- `POST /mcp`（[`backend/app/routes/mcp.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/routes/mcp.py)）
- `GET /integration/manifest.json`（[`backend/app/routes/system.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/routes/system.py)）
- `GET /api/health`、`GET /api/debug-config`

## 6. 前端页面路由

前端路由定义：[`frontend/src/routes.js`](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/routes.js)

- `/`：首页
- `/api/auth/callback`：前端 OAuth 回调页
- `/bookshelf`：书架页
- `/workbench/library-import`：模板导入工作台
- `/story/result`：阅读/结果页
- `/stories`：历史页

当前前端体验补充：

- 书架页的自定义故事生成支持长等待提示、失败分类和稍后重试。
- 阅读页改为正文完整 reveal 后才展示选项区。
- “我的自定义故事”会区分继续互动与重新开始，并在本地自动清理旧重复卡片。

## 7. 文档状态说明

以下文档已归档为历史方案，不再代表当前实现：

- [`docs/archive/legacy/story-loading-pipeline-legacy.md`](/Users/pipilu/Documents/Projects/potato-novel/docs/archive/legacy/story-loading-pipeline-legacy.md)
- [`docs/archive/legacy/story-system-redesign-proposal.md`](/Users/pipilu/Documents/Projects/potato-novel/docs/archive/legacy/story-system-redesign-proposal.md)
- [`docs/archive/legacy/prd-multiplayer-story-mode-draft.md`](/Users/pipilu/Documents/Projects/potato-novel/docs/archive/legacy/prd-multiplayer-story-mode-draft.md)
