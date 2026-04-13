## CHANGED Requirements

### Requirement: Custom story generation SHALL expose generation-stage language
The UI SHALL present custom story creation as generation work rather than loading fixed content, and that language SHALL remain specific enough for users to distinguish pending generation from timeout, network interruption, and unrecoverable failure.

#### Scenario: Generation status stays specific while pending
- **WHEN** a custom story is still being generated
- **THEN** the visible status language SHALL describe the request as actively generating
- **AND** the copy SHALL not be reused as a generic error placeholder

#### Scenario: Generation failure is categorized for the user
- **WHEN** a custom story request fails
- **THEN** the surfaced message SHALL distinguish timeout, network interruption, or backend failure when that classification is available
- **AND** the user SHALL receive a retry-oriented next step

### Requirement: Custom story generation SHALL accept optional style guidance
The custom-story generation workflow SHALL accept an optional user-provided style or direction hint alongside the opening, and the generation pipeline MUST treat that hint as a creative constraint rather than discarding it.

#### Scenario: Style hint is submitted with opening
- **WHEN** a user provides both an opening and an optional style or direction hint
- **THEN** the frontend SHALL include both fields in the custom generation request
- **AND** the backend SHALL make the hint available to prompt construction for the generated package
