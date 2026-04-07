## Why

当前 `backend/app/main.py` 仍同时承担 HTTP 路由、session 存储、library seed 编排、story runtime 推进和部分 provider 协调职责，导致后端在持续演进 library/custom 双模式时回归风险高、评审成本高、改动边界不清。与此同时，文件与函数级中文说明缺乏统一规范，新成员很难快速判断模块职责和函数意图。

现在需要把后端结构继续拆到可维护边界，并把“文件用途说明 + 合理中文函数注释”沉淀为明确约束，避免后续重构成果再次退化回单文件堆叠。

## What Changes

- 将后端入口重构为“`main.py` 负责 app 创建与 router 挂载，领域逻辑下沉到 routes / services / providers / repositories / domain” 的分层结构。
- 按职责拆分路由模块，至少区分 `auth`、`library`、`stories`、`sessions`、`mcp` 五类 HTTP 入口。
- 抽离 story runtime、library seed、story generation 等服务层，收敛运行时推进、首访播种、两阶段生成与 hydrate 编排。
- 抽离 stories / sessions repository，统一 JSON 文件存储与数据库存储读写入口。
- 收敛 provider 相关逻辑，明确豆包 / SecondMe 的调用边界，以及 prompt 构造与模型输出解析职责。
- 新增后端代码注释规范：
  - 每个模块文件顶部必须说明文件用途与职责边界
  - 公开函数必须带合理中文 docstring
  - 复杂私有函数必须带合理中文 docstring
  - 行内注释只在解释关键意图、约束或非显然决策时使用
- 在迁移过程中保持现有对外 API 能力稳定，避免引入与本次架构整理无关的功能变化。

## Capabilities

### New Capabilities
- `backend-module-architecture`: 定义后端按 routes / services / providers / repositories / domain 分层后的职责边界与依赖方向。
- `backend-code-documentation-standards`: 定义后端模块文件用途说明和中文函数注释的统一规范。

### Modified Capabilities

## Impact

- 主要影响 [`backend/app/main.py`](/Users/pipilu/Documents/Projects/potato-novel/backend/app/main.py) 以及后续新增的 `routes/`、`services/`、`providers/`、`repositories/`、`domain/` 目录。
- 影响 OAuth、library seed、story session、story runtime、MCP 等后端入口的组织方式，但目标是不改变现有对外 API 合约。
- 影响代码评审标准与团队编码规范，需要在新旧模块迁移期间同步执行注释规范。
- 后续实现需要补充分层后的回归验证，确保 storage、seed、runtime、story playback 不因目录迁移产生行为回退。
