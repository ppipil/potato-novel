# 小说加载链路说明

这份文档描述当前项目里，从书架点击进入故事，到故事页继续推进、补节点、生成选项、保存结局的完整链路。

> `2026-04` 差异说明（相对本文旧段落）：
> - 书架生成交互已改为非阻塞等待，页面可继续浏览；生成成功后可从书架提示继续进入结果页。
> - 活跃阅读页主路径已以本地 runtime 推进为主，不再依赖每回合 hydrate 接口。
> - “局势提示”当前作为选择前上下文展示，不再进入历史 transcript 主流。
> - 结局保存主路径为前端本地 optimistic + `POST /api/story/save`；本文里旧的 finalize 描述仅作历史参考。

目标是回答 6 个问题：

1. 书架点击“开始”后，前后端各做了什么
2. 调用了哪些接口
3. 每一步分别用了什么模型
4. prompt 是怎么组织的
5. 得到了什么结果并写回了哪里
6. 做了哪些异常处理与回退

## 1. 总体架构

当前链路不是“一个模型生成整条故事”，而是三层分工：

- 结构层：后端模板控制
- 选项层：SecondMe `act/stream`
- 正文层：Volcengine / 豆包优先，未配置时回退到 SecondMe

对应代码：

- 结构模板：`backend/app/main.py` 里的 `_build_template_story_package_skeleton(...)`
- 选项生成：`backend/app/main.py` 里的 `_generate_story_node_choices(...)`
- 正文生成：`backend/app/main.py` 里的 `_generate_story_node_content(...)`

当前 story package 的 `debug` 字段也会记录这一层分工，生成于：

- `backend/app/main.py` 里的 `_story_generation_debug_metadata(...)`

## 2. 从书架点击“开始”的完整链路

### 2.1 前端入口

书架页入口在：

- `frontend/src/views/BookshelfPage.vue` 里的 `handleGenerate(...)`

它会先判断：

- 是模板 opening 还是自定义 opening
- 本地 `cacheStates` 里这个 opening 是否已经有可用 session
- 本地 `storySessionCache` 里是否已有可直接继续使用的 session

当前策略是：

- 模板故事如果已有未完成 session，优先复用
- 如果本地 session 已经 `completedRun`，则重新开一个新 session
- 如果没有可复用 session，则直接调用后端开始新故事

### 2.2 前端调用的接口

书架页真正调用的是：

- `frontend/src/lib/api.js` 里的 `startStorySession(payload)`
- 对应接口：`POST /api/story/start`

如果是拿旧 session，则会调用：

- `frontend/src/lib/api.js` 里的 `getStorySession(sessionId)`
- 对应接口：`GET /api/story/sessions/{session_id}`

### 2.3 后端 `/api/story/start`

接口位置：

- `backend/app/main.py` 的 `start_story(...)`

这个接口内部做的是：

1. 校验环境变量 `_require_env()`
2. 从 cookie session 里拿登录态 `_get_server_session(request)`
3. 调 `_create_or_reuse_story_package(body, server_session)`
4. 返回序列化后的 story session

返回结构核心是：

- `session.id`
- `session.meta`
- `session.package`
- `session.packageStatus`
- `reused`

## 3. 后端如何创建 story package

### 3.1 `_create_or_reuse_story_package(...)`

位置：

- `backend/app/main.py`

它先做复用判断：

- opening 一致
- role 一致
- 当前用户一致
- session `kind == story_package`
- 还没 `completedRun`
- `packageStatus` 是 `ready` 或 `hydrating`
- `generatedBy` 是当前允许的生成器版本

如果找到可复用 session，就直接返回。

如果没有，就进入新建流程：

1. 从登录 session 里取 SecondMe access token
2. 推导 persona profile `_derive_persona_profile(user)`
3. 调 `_build_story_package_two_stage(...)`
4. 把结果存入 sessions 持久层

### 3.2 `_build_story_package_two_stage(...)`

位置：

- `backend/app/main.py`

虽然名字还叫 `two_stage`，但现在的含义是：

1. 先生成模板骨架
2. 再给需要首屏可玩的节点补选项和正文

它的执行顺序是：

1. 调 `_build_template_story_package_skeleton(opening, role)`
2. 算首批要 hydrate 的节点 id
3. 对首批 `turn` 节点生成选项
4. 对首批节点生成正文
5. 没有首批生成的节点，保留 `loaded: false`
6. 组装成 package，做校验，再 finalize

### 3.3 当前的故事骨架

骨架不是实时模型生成，而是固定模板：

- `N1`
- `N2-soft`
- `N2-tease`
- `N2-hard`
- `N3-confession`
- `N3-secret`
- `N4-climax`
- `E-sweet`
- `E-slowburn`
- `E-open`

也就是：

- 4 个过程阶段
- 3 个结局节点

这个模板在：

- `backend/app/main.py` 的 `_build_template_story_package_skeleton(...)`

### 3.4 首屏默认 hydrate 哪些节点

位置：

- `backend/app/main.py` 的 `_initial_hydrate_node_ids(...)`

逻辑是：

- 先 hydrate 根节点 `N1`
- 再 hydrate 根节点三个选项直接能到的下一层节点

当前默认首批通常是：

- `N1`
- `N2-soft`
- `N2-tease`
- `N2-hard`

所以首次进入故事时，并不是只生成第一页。

## 4. 选项生成链路

### 4.1 用的模型和接口

选项始终走 SecondMe：

- provider：SecondMe
- 接口：`POST https://api.mindverse.com/gate/lab/api/secondme/act/stream`
- 代码：`backend/app/main.py` 的 `_call_secondme_act(...)`

当前代码里没有显式传底层 `model` 参数，所以日志里按：

- `model: secondme-default`

来标识。

### 4.2 选项生成入口

位置：

- `backend/app/main.py` 的 `_generate_story_node_choices(...)`

调用时机有两类：

1. 开始故事时，给首批 hydrated turn 节点生成选项
2. 后续点击到未加载节点时，给目标节点生成选项

### 4.3 选项 prompt 怎么组织

prompt 由：

- `_build_json_story_choice_instruction(...)`
- `_compose_story_choice_prompt(...)`

拼出来。

prompt 核心约束有：

- 必须输出严格 JSON
- 必须返回 3 个 choices
- 每个 choice 要有明显差异
- 不允许改写剧情结构
- 不允许改 `nextNodeId`
- 不允许自由新增剧情分支

上下文会带上：

- 故事标题
- 玩家身份
- 开头 opening
- 当前节点 id / kind / stageLabel
- 当前节点剧情功能 `beat`
- 当前节点摘要
- 当前节点局势提示 `directorNote`
- 当前节点要求的 3 种策略
- 完整骨架摘要

### 4.4 选项返回结果怎么用

模型返回后会进入：

- `_normalize_story_node_choices(raw_text, node)`

这里会做：

- JSON 解析
- 数量校验
- 去重
- 文案清洗
- 如果缺项或重复，就回退到 blueprint 里的 fallback 文案

最终生成的 choice 至少包含：

- `id`
- `text`
- `nextNodeId`
- `style`
- `tone`
- `effects`

### 4.5 选项生成的异常处理

`_generate_story_node_choices(...)` 会最多重试 3 次。

每次失败后会把失败原因拼进下一次的 repair hint。

如果 3 次都失败：

- 不会让整个故事直接崩掉
- 会回退到后端模板里预置的 `choiceBlueprints` / `fallbackText`

这一步是有兜底的。

## 5. 正文生成链路

### 5.1 用的模型和接口

正文优先走 Volcengine：

- provider：Volcengine / 豆包
- 接口：`POST {VOLCENGINE_BASE_URL}{VOLCENGINE_CHAT_PATH}`
- 当前你的配置通常是：
  - `VOLCENGINE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3`
  - `VOLCENGINE_CHAT_PATH=/chat/completions`
  - `VOLCENGINE_MODEL=doubao-seed-2-0-pro-260215`

代码位置：

- `backend/app/main.py` 的 `_call_volcengine_prose(...)`

如果 Volcengine 没配好，则回退到：

- SecondMe `act/stream`

入口仍然是：

- `_generate_story_node_content(...)`

### 5.2 正文 prompt 怎么组织

prompt 由：

- `_build_json_story_node_instruction(...)`
- `_compose_story_node_prompt(...)`

拼出来。

它要求模型：

- 返回严格 JSON
- 只返回节点正文所需字段
- 不输出 choices
- 不改骨架
- 不新增主线
- 更像有戏的互动小说场景，而不是平铺直叙总结

上下文包含：

- 故事标题
- 玩家身份
- 故事开头
- 当前节点 id / kind
- 当前节点阶段 `stageLabel`
- 当前节点戏剧功能 `beat`
- 当前节点路径摘要 `pathSummary`
- 当前节点摘要 `summary`
- 当前节点选项
- 完整骨架摘要

### 5.3 正文返回结果怎么用

模型结果会进入：

- `_normalize_story_node_content(raw_text)`

它会要求并整理这些字段：

- `stageLabel`
- `directorNote`
- `scene`
- `summary`
- `paragraphs`

然后写回节点，节点会被标记：

- `loaded: true`

### 5.4 正文异常处理

`_generate_story_node_content(...)` 也会最多重试 3 次。

如果 Volcengine 调用失败，常见错误会在 `_call_volcengine_prose(...)` 里抛出：

- `Volcengine prose provider is not configured`
- `Volcengine prose request failed`
- `Volcengine prose response missing choices`
- `Volcengine prose response was empty`
- `Unable to reach Volcengine prose API`

如果正文 3 次都无法被 normalize 成合法节点内容，最终会抛：

- `SecondMe returned invalid node content for {nodeId} after 3 attempts`

这里目前没有像选项那样强兜底的本地固定正文，所以正文失败会更容易直接让 hydrate/start 失败。

## 6. 进入故事页之后的恢复链路

故事页入口在：

- `frontend/src/views/StoryResultPage.vue`

### 6.1 首次进入

书架页在拿到 session 后会：

- `setTransferredStorySession(nextSession)`
- 同时写入 `sessionStorage`

故事页 `onMounted` 时优先消费：

- `consumeTransferredStorySession()`

如果拿到：

- 直接用这份 session 建立 runtime
- 不必再等一次后端请求

### 6.2 刷新页面后的恢复

如果刷新导致内存里的 transferred session 丢失：

1. 故事页先从 `sessionStorage` 里读取 `potato-novel-story-session`
2. 立即用本地 session 恢复页面
3. 再后台调用：
   - `GET /api/story/sessions/{session_id}`
4. 用服务端最新 session 静默刷新

这是为了避免刷新时一直卡在“正在进入故事...”

### 6.3 当前节点如果未加载怎么办

故事页现在有一个补偿逻辑：

- `ensureRuntimeNodeLoaded(sessionPayload, runtimePayload)`

如果恢复出来的 `runtime.currentNodeId` 指向的是一个 `loaded=false` 的节点：

- 前端会自动调用：
  - `POST /api/story/sessions/{session_id}/hydrate`
- 把当前节点补全，而不是只显示“后续剧情正在后台补全”

## 7. 点击选项之后的完整链路

### 7.1 前端入口

入口在：

- `frontend/src/views/StoryResultPage.vue` 的 `chooseOption(choice)`

点击后会：

1. 播放一个轻量翻页音效
2. 找 `choice.nextNodeId`
3. 判断目标节点是否已经 `loaded`

### 7.2 如果目标节点已加载

前端不会再请求后端，直接：

- 构造新的 `runtime.path`
- 追加 `runtime.entries`
- 用 `applyChoiceEffects(...)` 更新 state
- 如果目标节点是 `ending`，把 runtime 状态设为 `complete`

### 7.3 如果目标节点未加载

前端会调用：

- `frontend/src/lib/api.js` 的 `hydrateStorySession(sessionId, payload)`
- 对应接口：`POST /api/story/sessions/{session_id}/hydrate`

注意：

- 虽然仓库里还有 `/hydrate-stream`
- 但当前故事页已经切回稳定路径，实际使用的是普通 `/hydrate`

### 7.4 后端 `/api/story/sessions/{id}/hydrate`

位置：

- `backend/app/main.py` 的 `hydrate_story_session(...)`

逻辑是：

1. 校验登录态
2. 找到 story session
3. 确认 `kind == story_package`
4. 找出未加载的目标节点
5. 调 `_hydrate_story_package_nodes(...)`
6. 更新 `packageStatus`
7. 存回 sessions
8. 返回新 session

### 7.5 `_hydrate_story_package_nodes(...)`

这是后续节点补全的核心。

顺序是：

1. 遍历目标 pending node
2. 如果是 `turn` 节点，先调用 `_generate_story_node_choices(...)`
3. 再调用 `_generate_story_node_content(...)`
4. 用 `_apply_hydrated_node_content(...)` 把正文和选项写回节点
5. 更新 `hydratedNodeIds`
6. `finalize` package

所以当前后续节点补全是：

- 先生成选项
- 再生成正文

这也是为什么你会感受到 hydrate 仍然比较慢。

## 8. `/hydrate-stream` 现在是什么状态

后端仍然保留了：

- `POST /api/story/sessions/{session_id}/hydrate-stream`

它会：

1. 先生成选项
2. 再用 Volcengine 流式返回正文 chunk
3. 最后返回 `complete`

但当前前端故事页已经切回：

- `hydrateStorySession(...)`

也就是普通非流式接口。

所以目前线上行为应理解为：

- 有流式接口实现
- 但当前主路径没有在用它

## 9. 结局、保存与尾声签语

### 9.1 什么时候算“到达结局”

前端是这样判定的：

- 目标节点 `kind === "ending"`

在 `chooseOption(...)` 里一旦进入 ending 节点，会把 runtime 更新为：

- `status: "complete"`
- `endingNodeId`
- `summary`

### 9.2 保存前后的接口链路

故事页点“保存书架”后：

1. 前端先构造 `completedRun`
2. 调 `POST /api/story/finalize`
3. 后端把 `completedRun` 写回 session
4. 后端返回整理好的 story 文本和 meta
5. 前端再调 `POST /api/story/save`
6. 后端把最终故事保存到 stories 持久层

对应接口：

- `backend/app/main.py` 的 `finalize_story(...)`
- `backend/app/main.py` 的 `save_story(...)`

### 9.3 尾声签语

前端点“生成尾声签语”后会调用：

- `POST /api/story/analyze-ending`

后端会：

1. 如果有 `sessionId`，从已完成 session 里拿 opening / summary / transcript / state
2. 否则就从前端传入的 meta 里拼
3. 用 `_compose_ending_analysis_prompt(...)`
4. 调 `_call_secondme_chat(...)`
5. 用 `_normalize_ending_analysis(...)` 整理结果

也就是说：

- 尾声签语走的是 SecondMe chat
- 不是 Volcengine

## 10. 登录链路

虽然你这份文档重点是小说加载，但完整链路依赖登录，所以这里补一下：

1. 前端跳到 `/api/auth/login`
2. 后端写 `oauth_state` cookie 并跳转 SecondMe OAuth
3. 回调页 `/api/auth/callback` 拿到 `code + state`
4. 前端调：
   - `POST /api/auth/exchange`
5. 后端：
   - 校验 `oauth_state`
   - 调 token 接口换 access token
   - 再调 user info
   - 最后写 session cookie

接口位置：

- `backend/app/main.py` 的 `auth_exchange(...)`

## 11. 异常处理总表

### 11.1 书架页

- opening 为空：前端直接提示“先写一个故事开局”
- 本地缓存 session 异常：删除坏缓存，重新 `startStorySession`
- 已完成的模板 session：丢弃旧 session，重新开新故事

### 11.2 `/api/story/start`

- opening / role 缺失：400
- 登录态缺失：401
- 环境变量缺失：500
- 构建 story package 失败：抛 HTTPException

### 11.3 选项生成

- JSON 解析失败：重试
- 选项数量不足或重复：重试
- 3 次都失败：回退到 blueprint fallback

### 11.4 正文生成

- Volcengine 配置缺失：直接抛错
- 网络错误：502
- 上游响应为空：400
- 3 次 normalize 失败：502

### 11.5 hydrate

- session 不是 `story_package`：400
- `targetNodeId` 缺失：400
- target node 不存在：404
- hydrate 完成后会重算 `packageStatus`

### 11.6 finalize / save

- sessionId 缺失：400
- `completedRun` 缺失：400
- endingNodeId 不是 ending 节点：400
- story 为空：400

### 11.7 OAuth

常见错误：

- `Missing code or state`
- `OAuth state mismatch`
- `Token exchange failed`
- `Token response missing access token`
- `Failed to fetch user info`
- `Unable to reach SecondMe OAuth API`

前端回调页已经把这些错误翻译成了更清楚的人话。

## 12. 当前真实运行中的模型分工

一句话总结当前主链路：

- 书架点击开始：`POST /api/story/start`
- 后端模板生成骨架
- SecondMe `act/stream` 生成首批节点选项
- Volcengine / 豆包生成首批节点正文
- 故事页点击未加载节点：`POST /api/story/sessions/{id}/hydrate`
- SecondMe 先生成该节点选项
- Volcengine / 豆包再生成该节点正文
- 到结局后：`POST /api/story/finalize`
- 尾声签语：SecondMe `chat`
- 保存故事：`POST /api/story/save`

## 13. 目前最值得注意的几个实现事实

1. 当前主路径已经不是全模型生成骨架，而是后端模板骨架
2. 当前主路径的后续节点补全不是流式，而是普通 hydrate
3. hydrate 仍然偏慢，因为它是“先选项，后正文”串行执行
4. 选项有 fallback，正文没有同等级 fallback
5. 页面刷新时已经改成“本地先恢复，再后台同步”
6. 当前节点如果未加载，前端会自动补一次，不再只是挂着占位文案
