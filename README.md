# Potato Novel x SecondMe OAuth Demo

这是一个最小可运行骨架：

- `frontend/`：Vue 3 前端，承接 `http://localhost:3000/api/auth/callback`
- `backend/`：FastAPI 后端，负责发起 OAuth、校验 state、交换 token、保存 session

## 为什么回调还能保持 `localhost:3000`

你当前已经在 SecondMe 平台填写了：

```text
http://localhost:3000/api/auth/callback
```

这个仓库现在兼容这条回调地址：

1. 浏览器先访问后端 `/api/auth/login`
2. SecondMe 授权完成后跳回前端 `/api/auth/callback`
3. 前端回调页读取 `code` 和 `state`
4. 前端把它们 POST 给后端 `/api/auth/exchange`
5. 后端用 `Client Secret` 完成 token exchange，并建立 session

## 官方 OAuth 端点

我已经从官方文档确认了以下值，可直接填入 `backend/.env`：

- `SECONDME_AUTH_URL=https://go.second.me/oauth/`
- `SECONDME_TOKEN_URL=https://api.mindverse.com/gate/lab/api/oauth/token/code`
- `SECONDME_USERINFO_URL=https://api.mindverse.com/gate/lab/api/secondme/user/info`
- `SECONDME_SCOPE=user.info`

参考文档：

- [SecondMe API Quick Start](https://develop-docs.second.me/en/docs)
- [OAuth2 Integration Guide](https://develop-docs.second.me/en/docs/oauth2)

## 分层生成实验

当前故事生成正在往“结构层 / 表达层”拆分：

- 后端模板控制故事骨架、状态推进和结局路由
- SecondMe `act/stream` 负责节点选项生成
- 火山模型负责节点正文生成

本地需要额外配置这些环境变量：

- `VOLCENGINE_API_KEY`
- `VOLCENGINE_MODEL`
- `VOLCENGINE_BASE_URL`
- `VOLCENGINE_CHAT_PATH`，默认可用 `/chat/completions`

本地测试时把这些值写进 `backend/.env`，不要把真实 key 提交进仓库。部署到 Vercel 时请改用 Vercel 环境变量注入。

可以先用本地脚本单独验证正文链路：

```bash
cd /Users/pipilu/Documents/Projects/potato-novel/backend
python3 scripts/test_volcengine_prose.py
```

## 本地启动

### 1. 后端

```bash
cd /Users/pipilu/Documents/Projects/potato-novel/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

### 2. 前端

```bash
cd /Users/pipilu/Documents/Projects/potato-novel/frontend
npm install
cp .env.example .env
npm run dev
```

## 当前联调路径

1. 打开 `http://localhost:3000`
2. 点击 `使用 SecondMe 登录`
3. 完成授权
4. 浏览器回到 `/api/auth/callback`
5. 前端调用后端完成 token exchange
6. 登录成功后跳转 `/bookshelf`

## 审核材料可直接沿用

你已经准备好的测试流程可以继续用：

1. 访问应用首页
2. 点击 SecondMe 登录
3. 登录成功后进入“土豆小说”书架
4. 选择一本小说开头
5. 选择角色身份
6. 与其他 AI 分身或 NPC 一起推动剧情
7. 生成短篇小说结果页
