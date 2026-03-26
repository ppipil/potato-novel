## ADDED Requirements

### Requirement: The system SHALL generate reusable interactive story packages before active reading
The system SHALL support generating an interactive story package for an authenticated user before the user enters the active story page. A generated package MUST be associated with the selected opening, selected role, and requesting user.

#### Scenario: Bookshelf preloads a story package
- **WHEN** an authenticated user is on the bookshelf and provides an opening and role
- **THEN** the system can generate a story package for that opening and role without requiring the user to first enter the story page

#### Scenario: Ready package is reused for story entry
- **WHEN** the user opens a story whose matching package is already ready
- **THEN** the system returns that ready package instead of generating a new one for the same entry action

### Requirement: A story package SHALL contain a complete short interactive branch bundle
Each generated package MUST contain a branching structure covering at least 4 playable turns and at most 6 playable turns, exactly 3 choices for each playable turn, per-choice effect data, valid next-node references, and at least 1 ending node.

#### Scenario: Package passes minimum structural validation
- **WHEN** the backend marks a generated package as ready
- **THEN** the package includes 4-6 playable turns, three choices on each playable node, and at least one reachable ending node

#### Scenario: Every choice points to a valid next node
- **WHEN** a package is normalized after generation
- **THEN** each choice references an existing next node or ending node inside the same package

### Requirement: Users SHALL be able to request a fresh package
The system SHALL allow the user to explicitly discard the current draft package for an opening and request a newly generated package for the same opening and role.

#### Scenario: User regenerates from bookshelf
- **WHEN** the user chooses the "generate new" action for a package candidate on the bookshelf
- **THEN** the system creates a fresh package and does not force the user to keep using the prior draft package

#### Scenario: Regeneration does not reuse the superseded draft by default
- **WHEN** a fresh package has been successfully generated after an explicit regeneration request
- **THEN** subsequent story entry uses the newly generated package unless the user intentionally reselects an older saved artifact
