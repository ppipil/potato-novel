# SecondMe Integration Draft

当前项目已经补齐了创建 integration 所需的三块基础能力：

- skill 信息
- MCP endpoint
- manifest

## 本地可用地址

开发环境：

- MCP endpoint: `http://localhost:8000/mcp`
- manifest: `http://localhost:8000/integration/manifest.json`

## 当前 manifest 结构

manifest 对应平台前端中可确认的字段：

- `skill`
- `prompts`
- `actions`
- `mcp`
- `oauth`
- `envBindings`

当前这份 integration 暂定为：

- skill key: `potato-novel`
- display name: `土豆小说`
- tools:
  - `list_openings`
  - `generate_story`
  - `list_saved_stories`

## 当前阻塞项

要在 SecondMe Develop 真正创建并通过校验，至少还缺两项：

- `SECONDME_APP_ID`
  - 这是平台里的 app record id，不是 `client_id`
- 可公网访问的部署地址
  - 平台校验大概率不会接受 `localhost`

建议最终填写：

- `PUBLIC_BASE_URL=https://你的线上域名`
- `SECONDME_APP_ID=fa9db4c3-09e6-4ac9-86ad-07b598d99345`

## 当前已确认

- `confirmed`: 你的 `appId` 与 `client_id` 当前是同一个值
- `confirmed`: `SECONDME_APP_ID=fa9db4c3-09e6-4ac9-86ad-07b598d99345`

## 如果要在平台创建 integration

优先使用下面这些值：

- manifest URL: `https://你的线上域名/integration/manifest.json`
- MCP endpoint: `https://你的线上域名/mcp`
- required scopes:
  - `user.info`
  - `chat`

## 当前 MCP 鉴权说明

`generate_story` 工具当前设计为：

- 优先读取 `Authorization: Bearer <SecondMe access token>`
- 没有 bearer token 时返回明确错误

这是为了兼容平台后续可能通过 oauth app + header template 转发用户 token 的模式。

## 后续创建/校验步骤

1. 部署当前后端到公网
2. 在 `.env` 中填入 `PUBLIC_BASE_URL`
3. 在 `.env` 中填入 `SECONDME_APP_ID`
4. 去 `https://develop.second.me/integrations/edit/new` 创建 integration
5. 填入 manifest URL 或按当前结构手动填写
6. 执行 validate
7. 如果 validate 报错，按错误继续修复并重试
