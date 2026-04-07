## Context

当前系统已经实现了一版“后端模板骨架 + 运行时节点补全”的互动小说方案，但模板故事和自定义故事仍共用大量生成逻辑。结果是：

- 模板故事本应像现成互动小说一样稳定读取，却仍然会受到生成链路影响
- 自定义故事和模板故事共用一套状态词汇与 session 逻辑，概念不清晰
- `hydrate` 承担了过多职责，导致页面刷新、补节点、返回首页等行为都变得脆弱

新的设计目标不是继续优化旧链路，而是重新划分职责边界：

- 模板故事是固定内容资产
- 自定义故事是创建时生成的内容
- session 只保存游玩进度

## Goals / Non-Goals

**Goals**

- 模板故事进入和游玩时不再依赖运行时模型调用
- 自定义故事只在创建时调用模型，并统一使用豆包
- 将“内容资产”和“用户游玩进度”拆成不同的数据层
- 模板与自定义在生成完成后复用同一套 session 播放接口
- 去掉模板故事路径上的 `hydrate` 心智和下载式状态文案

**Non-Goals**

- 不在本次设计中实现完整的内容编辑后台
- 不在本次设计中引入新的推荐/人格判断功能
- 不在本次设计中要求自定义故事支持边玩边继续生成
- 不在本次设计中重写 OAuth、用户体系或历史故事存储格式

## Decisions

### 1. 模板故事定义为预生成内容资产

模板故事将以完整 story package 的形式存储在后端，作为可复用公共内容供所有用户读取。

这意味着模板故事：

- 进入时不重新生成
- 游玩时不再补节点
- 刷新时只恢复 session

选择该方案而不是继续优化模板故事的 `hydrate`，是因为模板内容天然适合预生成，不应继续承担运行时生成复杂度。

### 2. 自定义故事定义为“创建时生成”

自定义故事仅在用户提交 opening 时进入模型调用链路，后端生成一整份可玩 package 后再进入阅读。

选择该方案而不是继续边玩边补节点，是因为创建时集中等待比游玩过程中反复等待更容易接受，也更容易解释。

### 3. 自定义故事统一使用豆包

自定义故事创建时不再采用 SecondMe + 豆包双模型协作，而改为只使用豆包。

推荐做法是仍然保持两步生成，但两步都由豆包完成：

- 第一步：生成骨架
- 第二步：补正文和选项

选择该方案而不是双模型协作，是因为单模型更容易调试、更容易校验、也更容易控制失败面。

### 4. session 只表示用户进度

session 将不再负责内容生成编排。它只记录：

- 关联的 package
- 当前节点
- 已走路径
- 当前状态
- 是否完成

选择该方案而不是让 session 同时承载内容补全，是因为 session 应该回答“用户玩到哪了”，而不是“内容还缺什么”。

### 5. 模板故事和自定义故事在游玩阶段统一接口

虽然模板和自定义在“创建 package”阶段不同，但一旦 package 已经就绪，两者的游玩接口应尽量统一。

统一后，前端故事页不需要根据来源类型维护两套播放行为。

## Data Model

### A. 模板故事内容资产

建议新增或明确一类后端持久化记录，例如：

- `library_story_packages`

字段建议：

- `id`
- `opening`
- `role`
- `title`
- `package_json`
- `version`
- `status`
- `created_at`
- `updated_at`

它表示：

- 一份已经完成的模板故事 package

### B. 用户故事会话

沿用或调整现有 `story_sessions`，但明确字段职责：

- `id`
- `user_id`
- `source_type` (`library` / `custom`)
- `package_id` 或 `package_json`
- `meta`
- `current_node_id`
- `path_json`
- `state_json`
- `completed_run_json`
- `status`
- `created_at`
- `updated_at`

规则：

- 模板故事 session 优先引用共享 package
- 自定义故事 session 第一版可以直接内嵌自己的 `package_json`

## API Shape

### 模板故事

- `GET /api/library-stories`
  - 返回模板故事目录

- `POST /api/library-stories/:id/start`
  - 创建或恢复该用户在此模板故事上的 session

### 自定义故事

- `POST /api/custom-stories/generate`
  - 输入 `opening + role`
  - 生成完整可玩的 custom story session

### 统一 session 播放

- `GET /api/story-sessions/:id`
  - 获取 session 与关联 package

- `POST /api/story-sessions/:id/choose`
  - 提交 `choiceId`
  - 后端推进 current node / path / state
  - 返回新的 session runtime

- `POST /api/story-sessions/:id/finalize`
  - 生成 completed run

- `POST /api/story-sessions/:id/analyze-ending`
  - 生成尾声签语

## Frontend Behavior

### 书架页

模板卡片只展示：

- 进入故事
- 继续游玩
- 已通关

不再展示：

- 下载
- 预缓存
- 重新缓存
- 即将完成

自由创作区域单独展示“生成故事”语义。

### 故事页

故事页在模板模式下只负责：

- 显示当前节点
- 播放文本
- 显示选项
- 提交选择
- 恢复与保存

不再承担模板故事补节点职责。

在自定义模式下，故事页也尽量只负责播放，而不是继续触发运行时生成。

## Migration Plan

1. 明确 session 的 `source_type`
2. 为模板故事建立完整 package 的后端存储与读取路径
3. 将模板故事入口改为读取预生成 package，不再依赖模板 `hydrate`
4. 将自定义故事入口改为“创建时全用豆包”
5. 用统一的 session 播放接口替换现有与来源耦合较重的故事推进逻辑
6. 下线模板故事路径上的下载/预缓存/重新缓存文案与状态

## Risks / Trade-offs

- 模板故事需要一套内容入库流程，短期可能先手工准备少量 package
- 自定义故事“创建时生成”可能比当前开始更慢，但中途会更顺
- 单模型全豆包会降低模型编排复杂度，但需要更严格的 schema 校验
- 如果自定义故事仍然过慢，后续可能需要在“生成完整 package”和“生成首个可玩 slice”之间做进一步取舍

## Open Questions

- 模板故事 package 第一版是手工导入，还是从现有模板链路离线产出？
- 自定义故事第一版是否必须生成完整全文，还是允许只生成完整主路径？
- 模板故事是否需要为不同 role 维护不同 package，还是 role 先只作为文案元信息？
