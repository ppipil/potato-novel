## ADDED Requirements

### Requirement: Node choices SHALL express visibly different dramatic strategies
每个过程节点的三个选项 MUST 在情绪姿态和戏剧策略上明显不同，例如“暧昧接球、嘴硬试探、强势掀桌”这类差异，而不是只有轻微措辞变化。

#### Scenario: Choice set contains materially different tones
- **WHEN** 系统为某个节点生成三条可选项
- **THEN** 用户能从文案上明确区分三种不同的互动姿态和可能后果，而不是看到三条近义选项

### Requirement: Node prose SHALL stay inside the backend-defined beat
节点正文生成 MUST 只补全当前节点的场景、对白和情绪，不得擅自新增骨架之外的新主线、新结局或新的结构性分支。

#### Scenario: Prose respects the node beat
- **WHEN** 正文模型收到某个节点的上下文、目标节拍和路径摘要
- **THEN** 返回内容只围绕该节点应完成的戏剧功能展开，并保持与既定骨架一致

### Requirement: Default prose output SHALL favor dramatic or comedic readability
默认正文输出 MUST 偏向短篇互动小说的 drama / 搞笑读感，优先使用可感知的动作、对白、误会、反应或情绪落点，而不是平铺直叙地总结剧情。

#### Scenario: Prose reads like an interactive-novel beat
- **WHEN** 系统完成某个节点的正文补全
- **THEN** 输出内容更接近可阅读的互动小说场景，而不是简短说明、系统提示或聊天式回答
