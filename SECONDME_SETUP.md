# SecondMe 联调与信息提交清单

这份清单用于从 0 开始接入 SecondMe，并准备提交审核或 review。

## 当前状态

- confirmed: 已安装 Skill 到 `/Users/pipilu/.codex/skills/secondme-dev-assistant`
- confirmed: 平台前端中可见关键字段包括 `App Name`、`Client ID`、`Client Secret`、`Redirect URI`、`OAuth`、`MCP`、`manifest`、`website`、`privacy`、`logo`、`summary`、`description`、`category`、`validate`、`release`、`review`、`submit`
- inferred: 你的接入流程大概率分成两块
  1. 外部应用 OAuth 信息配置
  2. Integration 或 MCP 信息配置、校验、提审
- missing: 当前仓库还是空目录，尚未有可联调的项目代码

## 第 1 阶段：先在 SecondMe Develop 拿到应用凭据

在 `https://develop.second.me` 完成或确认以下信息：

- `App Name`
- `Category`
- `Summary`
- `Description`
- `Website`
- `Privacy Policy URL`
- `Logo`
- `Redirect URI`

创建完成后，记录：

- `Client ID`
- `Client Secret`

安全要求：

- 不要把 `Client Secret` 发到聊天里
- 优先放到本地环境变量或密码管理器
- 如果平台提示只展示一次，立刻保存

建议本地变量名：

```bash
SECONDME_CLIENT_ID=
SECONDME_CLIENT_SECRET=
SECONDME_REDIRECT_URI=
```

## 第 2 阶段：准备联调必需信息

如果你要做 OAuth 登录，至少需要这些信息：

- 你的应用运行地址
- OAuth 回调地址 `Redirect URI`
- 登录成功后的前端跳转页
- 服务端交换 token 的接口路径
- 需要的 scopes

如果你要做 MCP / integration，还需要：

- integration 名称
- integration 简介
- manifest 地址或 manifest 内容
- 实际服务 endpoint
- 鉴权方式
- 测试账号或 reviewer 可验证方式

## 第 3 阶段：联调前自查

在提交 review 前，逐项确认：

- `Client ID` 与 `Redirect URI` 和代码中的配置一致
- 所有线上 URL 都可访问
- `Website`、`Privacy Policy URL`、`Logo` 不是占位内容
- OAuth 回调成功后能完成登录
- 如果有 token 刷新逻辑，过期后能自动续期
- manifest 中的 endpoint 与真实服务一致
- reviewer 不需要额外猜测就能完成测试

## 第 4 阶段：信息提交建议模板

可以按下面这份模板准备提审材料：

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

## 现在最缺的内容

这部分已经根据当前确认的信息更新：

```md
你当前要做的是：
- [x] 仅做 SecondMe OAuth 登录
- [ ] 做 MCP / integration
- [ ] 两者都做

现有项目技术栈：
- 前端：Vue
- 后端：FastAPI
- 业务：进入“土豆小说”书架、选择小说开头、选择角色并生成短篇共创小说

应用线上地址：
- 暂无，待部署

- http://localhost:3000
- http://localhost:3000/api/auth/callback
- 暂未拿到 / 待填写
- 暂未拿到 / 待填写
- 暂无
- 暂无测试账号
- 测试流程可先提供：
  1. 访问应用首页
  2. 点击 SecondMe 登录
  3. 登录成功后进入“土豆小说”书架
  4. 选择一本小说开头
  5. 选择角色身份
  6. 与其他 AI 分身或 NPC 一起推动剧情
  7. 生成短篇小说结果页
```

## 当前阻塞项

现在的唯一硬阻塞是平台侧凭据尚未创建：

- missing: `Client ID`
- missing: `Client Secret`

在拿到这两个值之前，我们可以先完成项目结构、登录入口、回调处理和本地环境变量设计。

## 建议的下一步

按这个顺序推进会最稳：

1. 在 `https://develop.second.me` 创建应用并填写基础资料
2. 把开发回调地址先填成 `http://localhost:3000/api/auth/callback`
3. 记录 `Client ID` 和 `Client Secret`
4. 按 [SECONDME_OAUTH_IMPLEMENTATION.md](/Users/pipilu/Documents/Projects/potato-novel/SECONDME_OAUTH_IMPLEMENTATION.md) 开始实现
5. 本地跑通登录回调后，再补线上地址和审核资料
```
