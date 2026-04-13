## Why

最新一轮用户反馈集中暴露出几个高频可感知问题：阅读页在正文收束前就跳到选项，结尾保存缺少明确反馈且可能重复入架，段落拆分会把引号语句切坏，自定义生成在慢网或失败时提示不够可靠，自由创作也缺少对风格和走向的显式约束入口。现在需要把这些零散痛点整理成一次成体系的体验修复，并在实现前明确代码边界，避免继续把后端入口模块做得更重。

## What Changes

- 修正互动阅读页的回合展示节奏，让最后一段正文完整呈现后再进入选项态，避免自动滚动直接跳过最后一拍内容。
- 调整正文段落拆分规则，优先保留模型原始换段，并避免把成对引号中的连续语句错误拆开。
- 为自由创作入口增加可选的风格/走向约束输入，并把这些约束带入自定义故事生成链路。
- 细化自定义生成的长等待、超时和网络失败反馈，让用户能区分“仍在生成”“连接异常”“本次失败可重试”等状态。
- 为结局后的“保存书架”提供可见成功态、处理中态和幂等保存保护，避免同一会话重复保存出多个书架条目。
- 在实现阶段要求后端变更继续落在已有 route/service/provider/parser 分层中，并顺手补齐本次触及但尚不规范模块的说明与注释。

## Capabilities

### New Capabilities
- `story-save-and-bookshelf-sync`: 覆盖已完结故事的保存反馈、重复点击保护以及同一会话的去重入架行为。

### Modified Capabilities
- `interactive-story-reading-experience`: 调整正文 reveal 节奏、选项出现时机和段落切分后的阅读完整性。
- `bookshelf-dashboard-experience`: 调整自由创作区的输入能力与生成状态提示，使用户能补充风格/走向并理解等待中的状态。
- `custom-doubao-story-generation`: 调整自定义生成请求负载、状态语言和失败反馈，支持风格约束并区分超时/网络/服务端失败。

## Impact

- 主要影响前端阅读与保存流程：[frontend/src/views/StoryResultPage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/StoryResultPage.vue)。
- 影响书架自由创作入口和生成反馈：[frontend/src/views/BookshelfPage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/BookshelfPage.vue) 以及前端请求封装 [frontend/src/lib/api.js](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/lib/api.js)。
- 影响自定义故事生成提示词与文本解析边界：[backend/app/story_prompts.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/story_prompts.py)、[backend/app/story_text.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/story_text.py)、[backend/app/providers/parsers.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/providers/parsers.py)。
- 若保存去重需要补强后端幂等性，还会影响故事保存相关路由、service 或 repository 模块，但实现应继续避免向 [backend/app/main.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/main.py) 新增业务编排逻辑。
