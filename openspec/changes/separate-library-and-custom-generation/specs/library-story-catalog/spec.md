## ADDED Requirements

### Requirement: Library stories SHALL be fixed packages
The system SHALL treat library stories as prebuilt interactive story packages stored in persistent storage. A library story package SHALL be shared across users and SHALL NOT require per-user runtime generation before reading.

#### Scenario: Entering a library story
- **WHEN** a user opens a story from the library or bookshelf template area
- **THEN** the backend returns the stored package for that story
- **AND** the client enters local playback without requesting a new skeleton or runtime node generation

#### Scenario: Reusing the same library story across users
- **WHEN** two different authenticated users open the same library story
- **THEN** the system serves the same underlying story package content to both users
- **AND** user-specific state remains limited to reading progress, choices, and interpretation features

### Requirement: Library story progression SHALL not depend on runtime hydration
The system SHALL allow normal node progression for library stories without model-backed runtime hydration.

#### Scenario: Choosing within a library story
- **WHEN** a user selects an option in a library story
- **THEN** the system advances session progress using the stored package
- **AND** the progression does not require runtime prose or choice generation for that node

### Requirement: Library story UI SHALL express loading rather than generation
The library UI SHALL describe story access as loading or entering fixed content. It SHALL NOT present library stories with download, pre-cache, or regenerate wording that implies per-user story generation.

#### Scenario: Displaying a library story card
- **WHEN** the bookshelf renders a library story card
- **THEN** the visible status language uses loading or entering semantics
- **AND** the card does not label the action as download or pre-cache

#### Scenario: Rendering an empty library section
- **WHEN** there are no saved user stories or no available library items in the relevant shelf section
- **THEN** the UI shows an empty-state message
- **AND** the UI does not render a fake placeholder book as if it were a real story
