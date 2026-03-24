# SecondMe Skill 复盘与改进建议

这份文档用于总结今天实际使用 SecondMe 官方 skill 时暴露出来的问题，并整理后续可改进方向。

## 总体评价

这份 skill 的定位是对的：

- 它试图覆盖 app、OAuth、integration、review 全生命周期
- 也强调了不要盲目生成、要基于平台状态推进

但在真实使用过程中，存在一个明显问题：

- 它给的是“正确的工作流框架”
- 但缺少足够稳定、可执行、可校验的具体细节

结果就是：

- 适合作为流程提醒
- 不足以单独支撑从 0 到 1 完成集成和提审

## 今天暴露出的不足

### 1. `references/*.md` 不可直接使用

现象：

- 主 skill 文件能获取
- references 链接拉下来却是 HTML 壳

影响：

- skill 中提到的 Phase 说明无法真正展开
- 实操阶段缺少具体字段和步骤

建议：

- skill 的 reference 文件应提供稳定的原始 Markdown 地址
- 或者直接内嵌关键操作说明，而不是只做相对链接跳转

### 2. 没有给出足够明确的官方端点

今天实际需要手动确认的内容包括：

- OAuth authorize URL
- token URL
- user info URL
- chat stream URL

问题：

- skill 里没有把这些“高频且关键”的端点明确列出来

建议：

- 在 implementation guidance 中直接给出这些官方端点
- 同时标注哪些是稳定端点，哪些需要从控制台确认

### 3. integration 字段结构没有直接展开

今天最终是通过平台官网前端 bundle 才反推出 integration 的关键结构：

- `skill`
- `prompts`
- `actions`
- `mcp`
- `oauth`
- `envBindings`

问题：

- skill 本身没有把 manifest shape 直接写清楚
- 导致创建 integration 时需要反向推断

建议：

- skill 应内置一份最小合法 manifest 示例
- 对每个字段说明是否必填、默认值、常见错误

### 4. 没有明确区分 `appId` 与 `client_id`

今天我们能确认两者在这个 app 里恰好相同，但这属于“碰巧一致”，不是概念相同。

问题：

- skill 中没有明确提醒：
  - `client_id` 是 OAuth 凭据
  - `appId` 是 integration `oauth.appId` 所需字段

建议：

- 在 app bootstrap 和 integration 章节里明确区分这两个概念
- 给出如何从控制台 URL 中识别 `appId`

### 5. 没有提醒“integration validate 需要公网地址”

这是今天最关键的现实阻塞之一。

问题：

- 本地 `localhost` 虽然适合调试
- 但 integration validate 基本需要公网地址

建议：

- skill 应尽早提示：
  - 本地联调可以用 `localhost`
  - 真正 validate / release 前必须部署到公网
- 并附一个轻量部署建议

### 6. 没有覆盖 cookie 大小、session 策略等真实工程问题

今天真实遇到的问题包括：

- cookie 太大导致登录态丢失
- `.env` 覆盖顺序导致配置看似存在但实际没读到
- Python 版本兼容问题

这些不是平台概念问题，但会直接阻断接入。

建议：

- skill 至少提供一个“常见接入故障清单”
- 包括：
  - redirect_uri 不一致
  - cookie 未保存
  - token 返回结构不同
  - scope 不足
  - localhost / 127.0.0.1 混用

## 建议新增的 skill 能力

### 1. 增加“最小可运行模板”

建议内置：

- Next.js 模板
- Vue + FastAPI 模板
- Node Express 模板

这样 skill 不只是讲流程，还能直接产出起步骨架。

### 2. 增加“integration manifest 生成器”

输入：

- app 名称
- 功能描述
- mcp endpoint
- scopes
- tool 列表

输出：

- 一份最小可用 manifest
- 对应平台字段说明

### 3. 增加“validate 报错对照表”

建议按类型给出排查路径：

- endpoint 不可达
- manifest 非法
- oauth appId 错误
- required scopes 不足
- authMode 不匹配
- tool 名称与实际不一致

### 4. 增加“部署前检查”

在创建 integration 前给出 checklist：

- 是否公网可访问
- manifest URL 是否可打开
- MCP endpoint 是否响应
- OAuth scopes 是否已重新授权
- 是否有 reviewer 可复现路径

### 5. 增加“审查资料模板”

建议直接提供：

- integration summary
- reviewer notes
- test steps
- known limitations

## 对我们当前项目的直接启发

今天这个 skill 最有价值的是：

- 给了正确的流程框架
- 提醒了 integration / app / release 是同一条生命周期

今天这个 skill 最不足的是：

- 关键 reference 不可直接落地
- 真实字段和工程问题需要大量人工补齐

因此，对我们这个项目最合理的做法是：

- 把 skill 当成流程导航器
- 关键字段、manifest、MCP、部署、validate 报错仍需要项目内文档兜底

## 建议结论

如果后续继续做 SecondMe 项目，建议保留两层文档：

1. 平台流程层
   - 继续参考官方 skill

2. 项目执行层
   - 由项目仓库自己维护
   - 包括：
     - OAuth 配置
     - integration manifest
     - 部署方式
     - validate 常见问题
     - 审核材料模板

这样效率会比单独依赖 skill 高很多，也更稳定。
