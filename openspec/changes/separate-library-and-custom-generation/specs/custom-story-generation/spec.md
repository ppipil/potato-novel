## ADDED Requirements

### Requirement: Custom story generation SHALL be the only runtime content-generation path
The system SHALL treat user-authored custom openings as the only entry path that generates a new interactive story package at runtime. This generation flow SHALL remain separate from fixed library story access.

#### Scenario: Starting a custom story
- **WHEN** a user submits a freeform opening from the custom creation area
- **THEN** the backend starts a new story generation workflow for that opening
- **AND** the workflow does not reuse library loading semantics or wording

### Requirement: Custom story generation SHALL expose phase-based progress
The system SHALL provide phase-based generation status for custom stories, including at minimum skeleton creation, opening content preparation, first-branch preparation, and ready-to-enter states.

#### Scenario: Showing generation phases
- **WHEN** a custom story is being generated
- **THEN** the frontend receives and renders the current generation phase
- **AND** the status text explains what the system is doing in user-facing language

#### Scenario: Communicating expected waiting cost
- **WHEN** a user starts custom story generation
- **THEN** the UI shows an approximate duration or expectation note
- **AND** the note distinguishes generation work from simple story loading

### Requirement: Custom stories SHALL become enterable before full package completion
The system SHALL allow a custom story to enter reading mode once the opening scene and immediate next-step content are ready. It SHALL NOT require the entire story package to be fully hydrated before the user can start reading.

#### Scenario: Entering after the first playable slice is ready
- **WHEN** the root scene and initial reachable branches have been prepared
- **THEN** the frontend may enter the story
- **AND** remaining nodes may continue hydrating in the background

#### Scenario: Continuing generation after entry
- **WHEN** a user has already entered a newly generated custom story
- **THEN** the backend may continue preparing later nodes asynchronously
- **AND** the reading flow only blocks when the next required node is not yet available
