## Why

当前自由创作的“风格/走向”更像一段自由备注，而不是生成链路中的主控制项。用户即使输入了明确偏好，正文和选项也常常仍被默认的互动小说骨架牵回同一种味道，导致“填了风格但看不出来”。与此同时，`backend/app` 目录下仍有一批故事生成相关的根模块裸露在入口旁边，分层边界不够清晰，后续继续增强生成能力时很容易再次把逻辑堆回 `main.py`。

现在需要把自定义创作的风格控制升级为“单选标签 + 可选补充说明”的明确产品能力，并同步收敛故事生成相关模块的目录结构，让后续生成策略和提示词演进建立在更稳的后端分层上。

## What Changes

- 将自由创作的风格控制从自由文本为主，收敛为“单选风格标签 + 可选补充说明”。
- 第一版固定支持 `言情`、`悬疑`、`恐怖`、`搞笑` 四个标签，并要求每个标签在正文、选项与结局收束上体现明显差异。
- 让风格标签作为自定义故事生成的主控制项，贯穿前端请求、后端骨架选择、正文 prompt 和选项 prompt。
- 将补充说明降级为次要微调输入，只用于补充世界观或细节要求，不再承担主要风格分类职责。
- 规划并实施故事生成相关根模块的目录归位，继续压缩 `backend/app/main.py` 的业务负担，避免新增功能再次写回入口文件。

## Capabilities

### Modified Capabilities
- `bookshelf-dashboard-experience`: 自由创作区改为单选风格标签入口，并保留可选补充说明。
- `custom-doubao-story-generation`: 风格标签成为生成主约束，要求真实影响骨架、正文和选项，而不是仅作为 opening 附注。

### New Capabilities
- `backend-generation-module-organization`: 约束故事生成相关模块在 `routes / services / providers / domain / core` 分层中的归位策略，并限制入口文件继续膨胀。

## Impact

- 主要影响自由创作入口与请求负载：[frontend/src/views/BookshelfPage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/BookshelfPage.vue)、[frontend/src/lib/api.js](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/lib/api.js)。
- 影响自定义故事生成的 prompt 组合、骨架选择与节点补全链路：[backend/app/story_prompts.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/story_prompts.py)、[backend/app/main.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/main.py)、[backend/app/services/story_generation_service.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/services/story_generation_service.py)。
- 影响故事生成相关根模块的目录规划，优先覆盖 [backend/app/story_prompts.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/story_prompts.py)、[backend/app/story_text.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/story_text.py)、[backend/app/model_providers.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/model_providers.py)、[backend/app/openings.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/openings.py)、[backend/app/integration.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/integration.py)。
- 本次实现应继续遵守“薄 `main.py`”约束，新的业务编排优先落在 service/provider/domain 边界，而不是继续扩展 [backend/app/main.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/main.py)。
