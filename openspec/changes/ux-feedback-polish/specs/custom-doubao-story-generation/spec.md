## CHANGED Requirements

### Requirement: Custom story generation SHALL expose generation-stage language
Custom-story waiting language SHALL clearly indicate long-running generation and provide actionable user guidance instead of silent indefinite waiting.

#### Scenario: Long wait state provides actionable guidance
- **WHEN** custom generation exceeds the normal quick-response window
- **THEN** the UI explains that generation may take minutes
- **AND** the UI provides explicit next actions such as waiting in background or retrying later

### Requirement: Custom story generation SHALL provide explicit failure feedback
The system SHALL distinguish timeout, unstable network, and generic generation failure in user-facing feedback.

#### Scenario: Timeout error is explicit
- **WHEN** custom generation request exceeds timeout limits
- **THEN** the user sees timeout-specific guidance rather than a generic failure message

#### Scenario: Network interruption is explicit
- **WHEN** request aborts due to unstable connectivity
- **THEN** the user sees network-specific retry guidance
