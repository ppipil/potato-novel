## MODIFIED Requirements

### Requirement: The system SHALL request a post-ending SecondMe analysis only for authenticated completion
After a player reaches an ending node, the system SHALL support one post-ending SecondMe analysis request only when the user has authenticated token context. Guest-mode completions MUST NOT trigger this request.

#### Scenario: Authenticated analysis is triggered after story completion
- **WHEN** an authenticated player reaches an ending node and requests the ending summary experience
- **THEN** the system sends the completed run context to SecondMe as a single post-ending analysis request

#### Scenario: Guest completion does not trigger ending analysis
- **WHEN** a guest player reaches an ending node
- **THEN** the system does not offer or trigger post-ending SecondMe analysis
- **AND** no analysis request is sent to SecondMe

#### Scenario: Intermediate turns do not trigger ending analysis
- **WHEN** the player is still on a non-ending node
- **THEN** the system does not request the post-ending analysis yet
