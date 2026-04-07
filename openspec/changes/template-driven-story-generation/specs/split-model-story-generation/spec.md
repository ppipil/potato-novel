## ADDED Requirements

### Requirement: Story option generation SHALL be separated from story prose generation
系统 MUST 将当前节点的选项生成和正文生成拆分成独立链路，不得再由单一运行时生成步骤同时负责结构、选项和正文。

#### Scenario: Separate providers handle options and prose
- **WHEN** 系统为某个模板节点补全可玩内容
- **THEN** 选项生成链路和正文生成链路分别接收各自输入，并分别返回选项结果和正文结果给后端编排层

### Requirement: SecondMe act generation SHALL be constrained to node-level choices
SecondMe `act/stream` 在这套模式下 MUST 只负责围绕当前节点输出三条可点击选项，不得要求其自由决定整张图的节点布局、结局数量或正文段落。

#### Scenario: Act stream returns choices for a known node
- **WHEN** 后端把某个已知节点的剧情意图、选项策略和上下文提交给 SecondMe
- **THEN** SecondMe 返回的内容被解释为当前节点的三个选项，而不是新的骨架或自由续写正文

### Requirement: Prose generation SHALL support a separate model provider configuration
节点正文生成链路 MUST 支持独立于 SecondMe 的模型提供方配置，包括独立的 base URL、model 标识和密钥注入方式，以便本地测试和部署时分别管理。

#### Scenario: Prose provider is configured separately
- **WHEN** 后端需要为某个节点生成正文
- **THEN** 它使用独立的正文模型配置读取 provider 参数，而不是复用 SecondMe 的认证或模型设置
