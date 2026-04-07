## Why

当前故事包虽然已经拆成“骨架生成 + 节点补全”两阶段，但结构和表达仍然主要依赖 SecondMe 实时生成，导致首次进入故事时等待明显，且分支差异、节奏控制和戏剧张力不够稳定。现在需要把故事生成进一步改成“后端模板控结构、不同模型分工做生成”的模式，先把性能和内容体验拉稳，再决定后续是否继续细化模板或扩展创作工作流。

## What Changes

- 引入一套由后端维护的高戏剧短篇互动故事骨架模板，用固定节点节奏、结局类型和状态推进规则来替代实时生成整张分支图。
- 将 SecondMe `act/stream` 的职责收敛为“当前节点选项生成”，要求它围绕已知节点意图和选项策略输出三条更有差异化、更有戏的选项文案。
- 新增一个独立的节点正文生成链路，使用火山侧模型根据后端给定的节点上下文、剧情意图和当前状态生成场景描述与角色台词。
- 由后端统一编排模板、选项生成、正文生成、状态推进和结局路由，不再让单一模型同时决定结构、选项和正文。
- 先以偏 drama / 搞笑风格的通用模板验证这套模式，暂不把网站扩展成完整互动小说编辑器。

## Capabilities

### New Capabilities
- `story-structure-templates`: 覆盖后端维护的通用高戏剧故事骨架模板、节点节奏、结局类型和状态推进约束。
- `split-model-story-generation`: 覆盖选项生成和正文生成的分层编排，以及后端对不同模型调用职责的控制。
- `dramatic-choice-and-prose-generation`: 覆盖节点选项的戏剧化输出要求，以及节点正文的风格、边界和上下文输入约束。

### Modified Capabilities

## Impact

- Affects backend story generation orchestration and package normalization in [backend/app/main.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/main.py).
- Affects backend runtime configuration in [backend/app/config.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/config.py) and environment-variable handling for the new model provider.
- Likely affects local and deployed secrets management through [backend/.env.example](/Users/pipilu/Documents/Projects/potato-novel/backend/.env.example) and Vercel environment-variable setup.
- May affect frontend loading and playback expectations in [frontend/src/views/BookshelfPage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/BookshelfPage.vue) and [frontend/src/views/StoryResultPage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/StoryResultPage.vue) because story packages will now come from backend templates plus split generation stages.
