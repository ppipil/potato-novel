## ADDED Requirements

### Requirement: The system SHALL request a post-ending SecondMe analysis after local completion
After a player reaches an ending node in a local story package, the system SHALL support one post-ending SecondMe request that analyzes the completed run using the opening, selected path, ending summary, and final state.

#### Scenario: Analysis is triggered after story completion
- **WHEN** the player reaches an ending node and requests the ending summary experience
- **THEN** the system sends the completed run context to SecondMe as a single post-ending analysis request

#### Scenario: Intermediate turns do not trigger ending analysis
- **WHEN** the player is still on a non-ending node
- **THEN** the system does not request the post-ending analysis yet

### Requirement: Ending analysis SHALL return normalized insight fields
The normalized post-ending response MUST include potato persona labels, romance-oriented analysis, life-oriented commentary, and a next-universe recommendation hook.

#### Scenario: Analysis includes all required fields
- **WHEN** the system returns a successful ending analysis
- **THEN** the response includes fields for potato persona labels, romance analysis, life commentary, and next-universe recommendation text

#### Scenario: Story history can display the normalized ending analysis
- **WHEN** a completed story is opened from history
- **THEN** the system can display the same normalized analysis fields without relying on freeform unstructured rendering
