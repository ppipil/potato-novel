## Context

当前后端虽然已经把 prompt、provider、text 处理拆出了一部分模块，但 [`backend/app/main.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/main.py) 仍然同时承担以下职责：

- FastAPI app 初始化与 middleware 配置
- OAuth、library、stories、sessions、MCP 等 HTTP 路由
- session / story 持久化读写
- library seed 的查找、抢锁、生成中占位、复用与回退
- story runtime 初始化、推进、finalize
- 部分 story package 组装与 provider 协调

这种结构在 library/custom 双模式已经成型的前提下，会持续带来两个问题：

- 单文件改动面太大，任何一条链路的调整都容易误伤其他模式
- 模块职责和函数意图不够显式，评审与接手成本不断升高

本次设计目标是在不改变现有对外 API 行为的前提下，把后端演进到更清晰的领域分层，并把代码说明规范一起落地。

## Goals / Non-Goals

**Goals:**

- 让 `main.py` 只保留 app 创建、middleware 配置与 router 挂载职责
- 按 `routes -> services -> repositories/providers/domain` 的方向重建依赖边界
- 拆分 story generation、story runtime、library seed 等高耦合领域逻辑
- 收敛 stories / sessions 的存储访问入口，避免服务层直接散落读写 JSON/DB
- 为后端模块建立统一中文说明规范，降低维护和评审成本
- 在迁移过程中保持现有 HTTP 路由、认证边界和 demo 体验稳定

**Non-Goals:**

- 不在本次设计中改动前端路由结构或重做 UI 状态机
- 不在本次设计中引入新的数据库表或强制切换持久化方案
- 不在本次设计中改变 OAuth 安全边界、cookie 结构或对外 API 路径
- 不在本次设计中把所有 Python 文件一次性全部注释重写到最完美状态

## Decisions

### 1. 采用“薄路由 + 服务编排 + 仓储访问 + 领域规则”分层

目标目录采用下面的稳定结构：

- `backend/app/main.py`
- `backend/app/routes/`
- `backend/app/services/`
- `backend/app/providers/`
- `backend/app/repositories/`
- `backend/app/domain/`

依赖方向约束如下：

- `routes` 负责请求解析、调用服务、返回响应
- `services` 负责业务编排和跨模块流程
- `repositories` 负责 stories / sessions 的持久化与查询
- `providers` 负责外部模型调用、prompt 构造、输出解析
- `domain` 负责纯规则、数据标准化、校验与模型无关的运行时逻辑

选择这条分层路线，而不是简单把 `main.py` 函数机械搬到多个文件，是因为真正需要降低的是耦合和依赖方向，而不是文件长度本身。

### 2. 路由先按现有 API 边界拆分，不在本轮改变路径

路由模块优先拆成：

- `routes/auth.py`
- `routes/library.py`
- `routes/stories.py`
- `routes/sessions.py`
- `routes/mcp.py`

每个模块内部继续保留当前 API 路径和入参/出参结构。这样可以先完成代码组织调整，再逐步做更细的领域优化，避免架构重构和 API 变更耦合在同一次迁移里。

### 3. service 层按高变更领域拆分，而不是按 CRUD 拆分

优先拆出以下服务：

- `story_generation_service`: 负责首访整包生成、两阶段生成、hydrate 编排
- `story_runtime_service`: 负责 runtime 初始化、choice 推进、completed run 组装
- `library_seed_service`: 负责 library seed 的加载、生成、复用、并发保护

选择这种拆分，而不是先统一成一个“大 session service”，是因为当前最复杂、最易回归的逻辑恰好集中在 generation / runtime / seed 三块，先拆这些能最快降低主文件认知负担。

### 4. 持久化统一下沉到 repository，服务层不得直接操作 JSON/DB 细节

`stories_repo.py` 与 `sessions_repo.py` 统一负责：

- JSON 文件 / DB 两种存储模式切换
- 记录的加载、保存、upsert、删除
- seed / session / story 的查询辅助

选择 repository 层，是为了避免 library seed、story runtime、stories 保存等服务各自再去直接碰 `_load_sessions()`、`_save_sessions()` 一类函数，从而让持久化分歧继续扩散。

### 5. domain 层承接“纯规则与纯数据结构”，优先迁移最稳定的规则

`domain/story_package.py` 和 `domain/session_models.py` 用于承接：

- package 校验、规范化、finalize 相关规则
- `sourceType`、runtime、session 序列化与结构辅助
- 与 HTTP、存储、外部 provider 无关的纯函数逻辑

这样可以给后续单元测试留下稳定落点，也避免 service 文件继续膨胀。

### 6. 注释规范只要求“准确、必要、可维护”，不追求注释数量

统一规范如下：

- 每个后端模块文件顶部必须有简短中文说明，描述文件用途、边界和不负责的内容
- 公开函数必须有中文 docstring
- 复杂私有函数必须有中文 docstring
- 行内注释只用于解释设计意图、约束、兼容性或非显然决策
- 不强制为显而易见的一行赋值、简单 getter、明显控制流补注释

选择这套规则，而不是“每一行都注释”，是为了避免注释噪音和后续维护负担。

### 7. 采用渐进迁移而不是一次性重写

迁移顺序建议为：

1. 拆 `routes`
2. 拆 `story_runtime_service` 与相关 domain 规则
3. 拆 `providers`
4. 拆 `repositories`
5. 拆 `library_seed_service` 与 `story_generation_service`
6. 最后清理 `main.py` 中残留 helper，并补齐注释

选择渐进迁移，是因为当前代码树已经存在进行中的业务演进，分阶段提交更容易控制回归面，也更适合和现有脏工作树共存。

## Risks / Trade-offs

- [风险] 重构期间容易出现函数搬迁后导入遗漏或循环依赖
  → 通过明确依赖方向、每阶段只迁一个边界、完成后立刻跑编译/构建检查来降低风险

- [风险] service / repository / domain 的边界在前两轮可能需要微调
  → 先用最小公开接口落地，避免一开始就设计过多抽象

- [风险] 注释规范执行过度会导致噪音和 review 负担上升
  → 在 spec 中明确“只要求合理中文说明，不要求注释密度”

- [风险] 路由拆分后如果顺手改动行为，排查会变难
  → 约束首轮迁移只做组织调整，不做无关逻辑变更

- [风险] library/custom 双模式的共享逻辑拆分不当会出现重复代码
  → 把共享规则尽量下沉到 domain / runtime service，避免在 route 层分叉

## Migration Plan

1. 创建 `routes/`、`services/`、`providers/`、`repositories/`、`domain/` 目录，并为每个模块加入文件头中文说明
2. 先迁移现有路由函数到对应 route 模块，在 `main.py` 中只保留 app 初始化与 router 挂载
3. 迁移 runtime 相关纯逻辑到 `story_runtime_service` 与 domain 模块，并保持 sessions 路由行为不变
4. 迁移 provider、prompt、parser 相关入口，统一 story generation 的外部依赖
5. 迁移 stories / sessions 持久化读写到 repository
6. 迁移 library seed 与 story generation 编排到独立 service
7. 清理 `main.py` 中残余 helper，补齐模块与函数中文 docstring
8. 对关键链路执行回归验证：OAuth、书架入口、library seed、custom 生成、session choose、finalize、save、MCP

回滚策略：

- 保持每一轮迁移为独立提交
- 任何一轮若出现高风险回归，可只回滚当轮模块迁移，不影响其他已稳定的拆分

## Open Questions

- `story_generation_service` 是否要在第一轮就覆盖所有 hydrate 相关逻辑，还是先只接住两阶段整包生成？
- `domain/session_models.py` 是保留 dict-based helper，还是开始引入 dataclass / typed models？
- 注释规范是否只对 `backend/app/` 生效，还是后续也扩展到 `backend/scripts/`？
