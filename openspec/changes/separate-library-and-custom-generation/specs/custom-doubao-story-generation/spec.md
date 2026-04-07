## ADDED Requirements

### Requirement: Custom story generation SHALL be separate from library story entry
The system SHALL treat user-authored custom openings as a distinct generation workflow. It SHALL NOT reuse library-story loading semantics for custom creation.

#### Scenario: Starting a custom story
- **WHEN** a user submits a freeform opening from the custom creation area
- **THEN** the backend starts a dedicated custom story generation workflow
- **AND** the resulting story is tracked as a `custom` source session

### Requirement: Custom story generation SHALL use Doubao only
The system SHALL use Doubao as the only runtime content-generation model for custom story creation.

#### Scenario: Creating a custom story package
- **WHEN** a custom story is generated
- **THEN** the backend uses Doubao for structure generation
- **AND** the backend uses Doubao for prose and choice completion
- **AND** the flow does not require a SecondMe content-generation call

### Requirement: Custom story generation SHALL complete before normal reading begins
The system SHALL produce a ready-to-play package for a custom story before handing control to the normal reading flow.

#### Scenario: Entering a generated custom story
- **WHEN** a custom story generation request succeeds
- **THEN** the frontend receives a playable story package through the session payload
- **AND** subsequent node progression does not depend on runtime hydration under normal play

### Requirement: Custom story generation SHALL expose generation-stage language
The UI SHALL present custom story creation as generation work rather than loading fixed content.

#### Scenario: Rendering custom-story progress
- **WHEN** a custom story is being created
- **THEN** the visible status language describes generation
- **AND** the wording does not reuse download, pre-cache, or library-loading terms
