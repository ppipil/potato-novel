## ADDED Requirements

### Requirement: The system SHALL build story packages from backend-defined structure templates
故事包生成流程 MUST 先由后端选择或构造一个结构模板，再基于该模板生成节点内容，而不是让运行时模型自由生成整张分支图。

#### Scenario: Backend creates a template-driven package skeleton
- **WHEN** 已认证用户为某个 opening 和 role 请求新的故事包
- **THEN** 后端先产出一个合法的模板化骨架，其中包含固定节点节奏、有效 next-node 关系、可达结局和初始状态字段

### Requirement: A default template SHALL enforce a high-drama short-story rhythm
默认故事模板 MUST 使用偏 drama / 搞笑的短篇节奏，至少包含“开场异常、局势升级、反转爆点、最终抉择”四个过程节点，以及三类结局。

#### Scenario: Default template uses dramatic beats
- **WHEN** 系统使用默认模板构造一个新故事包
- **THEN** 生成结果包含四个有明确戏剧功能的过程节点和三个结局节点，而不是松散的通用步骤

### Requirement: Structure templates SHALL define allowed state transitions and ending routing inputs
结构模板 MUST 明确定义每个节点允许的阶段、choice effects 的适用范围，以及会影响结局路由的状态输入，确保后端可以独立推进 relationship / persona 等运行时状态。

#### Scenario: Template provides state-routing contract
- **WHEN** 用户在本地播放时依次选择节点选项
- **THEN** 后端和前端都可以根据模板给定的 effects 和状态字段稳定推导下一步状态与可到达结局类型
