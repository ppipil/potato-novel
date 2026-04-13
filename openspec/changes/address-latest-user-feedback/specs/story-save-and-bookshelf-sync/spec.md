## ADDED Requirements

### Requirement: Completed stories SHALL provide deterministic save feedback
When a completed story is saved to the bookshelf, the product SHALL surface a stable saving lifecycle so users can tell whether the story is saving, already saved locally, or fully synced.

#### Scenario: Save action exposes visible progress and success state
- **WHEN** the user taps the save action for a completed story
- **THEN** the UI SHALL immediately show a saving state for that completed session
- **AND** after success it SHALL switch to a visible saved state instead of silently reverting to the original button copy

#### Scenario: Local-only fallback remains understandable
- **WHEN** local optimistic save succeeds but cloud sync fails
- **THEN** the product SHALL tell the user that the story already exists in the local bookshelf
- **AND** it SHALL clearly indicate that only the cloud sync needs retrying

### Requirement: Completed story save SHALL be idempotent per finished session
The system SHALL prevent the same finished story session from being inserted into the bookshelf multiple times through repeated taps, retries, or duplicate submissions.

#### Scenario: Repeat taps do not create duplicate bookshelf entries
- **WHEN** the user taps save multiple times for the same completed session
- **THEN** the UI SHALL block repeated submissions for that session
- **AND** the bookshelf SHALL keep only one saved entry for that completed session

#### Scenario: Retry after partial failure reuses the same save identity
- **WHEN** a previous save attempt already created a local or remote bookshelf entry for the completed session
- **THEN** a retry SHALL update or confirm the existing saved entry instead of creating a second one
