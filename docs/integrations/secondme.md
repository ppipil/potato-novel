# SecondMe 接入文档（合并版）

这份文档合并了原来的 `SECONDME_SETUP.md`、`SECONDME_OAUTH_IMPLEMENTATION.md`、`SECONDME_INTEGRATION.md`，作为项目唯一维护的 SecondMe 接入说明。

## 1. 接入范围

当前项目覆盖两部分：

- OAuth 登录（Vue 前端 + FastAPI 后端）
- Integration / MCP 接入（manifest + endpoint）

## 2. 当前已确认状态

- 前端本地地址：`http://localhost:3000`
- 后端本地地址：`http://127.0.0.1:8000`
- MCP endpoint（本地）：`http://localhost:8000/mcp`
- manifest（本地）：`http://localhost:8000/integration/manifest.json`
- 已确认 `SECONDME_APP_ID` 与当前 app record 对齐

## 3. 推荐 OAuth 架构

安全边界建议固定为：

- Vue：只负责登录入口、登录态页面与业务页面
- FastAPI：负责 OAuth 跳转、回调处理、token 交换、会话建立

当前实现使用前端回调页（代码对齐）：

- `http://localhost:3000/api/auth/callback`

## 4. 环境变量清单

```bash
SECONDME_CLIENT_ID=
SECONDME_CLIENT_SECRET=
SECONDME_REDIRECT_URI=http://localhost:3000/api/auth/callback
SECONDME_SCOPE=
SECONDME_AUTH_URL=
SECONDME_TOKEN_URL=
SECONDME_USERINFO_URL=
SESSION_SECRET=
FRONTEND_ORIGIN=http://localhost:3000
BACKEND_ORIGIN=http://127.0.0.1:8000

# integration 相关
PUBLIC_BASE_URL=
SECONDME_APP_ID=
```

## 5. 后端接口约定（OAuth）

- `GET /api/auth/login`：发起授权
- `POST /api/auth/exchange`：前端回调页拿到 `code/state` 后调用，后端完成 token 交换并建立会话
- `GET /api/me`：返回当前登录用户
- `POST /api/auth/logout`：退出登录

## 6. Integration / MCP 约定

### 6.1 manifest 关键字段

- `skill`
- `prompts`
- `actions`
- `mcp`
- `oauth`
- `envBindings`

### 6.2 当前工具集合

- `list_openings`
- `generate_story`
- `list_saved_stories`

### 6.3 提交平台时使用线上地址

- manifest URL：`https://<your-domain>/integration/manifest.json`
- MCP endpoint：`https://<your-domain>/mcp`

## 7. 联调顺序（推荐）

1. 在 SecondMe 平台创建/确认应用并拿到 `Client ID`、`Client Secret`
2. 配置回调地址并更新后端 `.env`
3. 打通 `/api/auth/login -> 前端 /api/auth/callback -> /api/auth/exchange -> /api/me`
4. 确认 manifest 与 MCP endpoint 本地可用
5. 后端部署到公网并设置 `PUBLIC_BASE_URL`
6. 在平台创建 integration 并执行 validate
7. 根据 validate 报错迭代修复

## 8. 常见问题清单

- `appId` 与 `client_id` 是不同概念；不要混用
- integration validate 通常不接受 `localhost`，必须公网地址
- cookie 不要塞入完整 token 和完整 user info，避免超长导致会话丢失
- 避免 `localhost` 与 `127.0.0.1` 混用导致回调不一致
- `redirect_uri`、scope、平台配置与代码配置必须完全一致

## 9. 提审材料模板

```md
App Name:
Category:
Summary:
Description:
Website:
Privacy Policy URL:
Redirect URI:

OAuth Scopes:

Integration Name:
Integration Summary:
Manifest URL:
Endpoint:
Auth Method:

Reviewer Notes:
1. 登录入口：
2. 测试步骤：
3. 测试账号：
4. 已知限制：
```

## 10. 历史文档归档

- 历史工作记录：[`docs/archive/worklogs/worklog-2026-03-24.md`](/Users/pipilu/Documents/Projects/potato-novel/docs/archive/worklogs/worklog-2026-03-24.md)
- 历史复盘：[`docs/archive/reviews/secondme-skill-review.md`](/Users/pipilu/Documents/Projects/potato-novel/docs/archive/reviews/secondme-skill-review.md)
