# SecondMe OAuth 实施方案

这份文档把当前项目明确收敛为一个 Vue + FastAPI 的 OAuth 登录方案。

## 项目目标

- confirmed: 当前只做 `SecondMe OAuth 登录`
- confirmed: 前端技术栈是 `Vue`
- confirmed: 后端技术栈是 `FastAPI`
- confirmed: 本地前端地址是 `http://localhost:3000`
- confirmed: 开发回调地址是 `http://localhost:3000/api/auth/callback`
- missing: `Client ID`
- missing: `Client Secret`
- missing: 线上部署地址

## 推荐架构

建议把 OAuth 的敏感逻辑都放在 FastAPI：

- Vue 负责展示登录按钮、登录态、书架和小说共创页面
- FastAPI 负责跳转 SecondMe 授权页、处理 callback、交换 token、保存 session

这样做的原因：

- `Client Secret` 不会暴露到前端
- 后续接用户信息、刷新 token、服务端鉴权都更自然
- 审核时更容易解释安全边界

## 推荐本地地址规划

为了避免前后端职责混乱，建议尽量改成下面这种分工：

- 前端：`http://localhost:3000`
- 后端：`http://localhost:8000`
- SecondMe OAuth callback：`http://localhost:8000/api/auth/callback`

如果你坚持把回调地址保留在 `http://localhost:3000/api/auth/callback`，也可以做，但前端需要再把 code 转发给 FastAPI 处理，链路会更绕。

## 推荐环境变量

建议至少准备这些变量：

```bash
SECONDME_CLIENT_ID=
SECONDME_CLIENT_SECRET=
SECONDME_REDIRECT_URI=http://localhost:8000/api/auth/callback
SECONDME_SCOPE=
SECONDME_AUTH_BASE_URL=
SECONDME_TOKEN_URL=
SECONDME_USERINFO_URL=
SESSION_SECRET=
FRONTEND_ORIGIN=http://localhost:3000
BACKEND_ORIGIN=http://localhost:8000
```

注意：

- `SECONDME_AUTH_BASE_URL`
- `SECONDME_TOKEN_URL`
- `SECONDME_USERINFO_URL`

这三个值要以 SecondMe 控制台或官方文档的实际地址为准，不要猜。

## 后端需要实现的接口

FastAPI 至少实现这几类接口：

### 1. 发起登录

```text
GET /api/auth/login
```

职责：

- 生成 `state`
- 可选生成 `code_verifier` / `code_challenge`
- 重定向到 SecondMe 授权地址

### 2. 处理回调

```text
GET /api/auth/callback
```

职责：

- 校验 `state`
- 读取 `code`
- 服务端向 SecondMe 交换 token
- 获取用户基础信息
- 建立你自己的 session
- 最后重定向到前端书架页

### 3. 当前用户信息

```text
GET /api/me
```

职责：

- 返回当前登录用户
- 供前端判断是否已登录

### 4. 退出登录

```text
POST /api/auth/logout
```

职责：

- 清空本地 session 或 cookie

## 前端需要实现的页面或动作

Vue 侧建议先做最小闭环：

- 首页
- `SecondMe 登录` 按钮
- 登录成功后的书架页
- 角色选择页
- 生成结果页

登录按钮行为建议直接跳转：

```text
window.location.href = "http://localhost:8000/api/auth/login"
```

前端不要自己拿 `Client Secret`，也不要直接在浏览器里交换 token。

## OAuth 联调顺序

按下面顺序联调最省时间：

1. 先在 SecondMe 平台创建应用
2. 填写 callback URL
3. 拿到 `Client ID` / `Client Secret`
4. 后端实现 `/api/auth/login`
5. 后端实现 `/api/auth/callback`
6. 前端接 `登录` 按钮
7. 前端用 `/api/me` 判断登录态
8. 登录成功后跳转书架页

## 需要你在 SecondMe 平台提交的信息

基于当前需求，建议先准备下面这套文案：

```md
App Name:
Potato Novel

Category:
Interactive Storytelling / Entertainment

Summary:
使用 SecondMe 登录后，用户可以进入土豆小说书架，选择开头与角色，并与 AI/NPC 共创短篇小说。

Description:
这是一个 Web Demo。用户通过 SecondMe 登录后，可以进入“土豆小说”书架，选择小说开头、角色身份，并与 AI 分身或 NPC 一起推动剧情，最终生成几千字以内的短篇小说结果页。

Website:
开发阶段可先留待部署后补充

Privacy Policy URL:
待补充

Redirect URI:
开发环境建议填写 http://localhost:8000/api/auth/callback
如果你必须以前端接回调，则保留 http://localhost:3000/api/auth/callback
```

## 审核说明建议

未来提交 review 时，可以用这段测试流程：

```md
1. 访问应用首页
2. 点击 SecondMe 登录
3. 登录成功后进入“土豆小说”书架
4. 选择一本小说开头
5. 选择角色身份（如男主 / 女主 / NPC）
6. 与其他 AI 分身或 NPC 一起推动剧情
7. 最终生成一篇几千字以内的短篇小说结果页
```

## 现在最值得先做的事

当前最优先的是两件事：

1. 去 SecondMe Develop 创建应用并拿到 `Client ID` / `Client Secret`
2. 把回调地址改成后端地址 `http://localhost:8000/api/auth/callback`

只要你拿到凭据，我下一步就可以直接帮你生成 Vue + FastAPI 的 OAuth 最小可运行骨架。
