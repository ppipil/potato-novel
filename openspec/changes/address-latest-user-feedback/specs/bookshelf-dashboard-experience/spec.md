## CHANGED Requirements

### Requirement: The dashboard SHALL support non-blocking generation waiting
When users start a story that may require long generation, the bookshelf experience SHALL provide visible progress and failure state without hard-locking the whole page, and the message SHALL distinguish ongoing generation from timeout or network failure.

#### Scenario: Long generation remains understandable
- **WHEN** a custom-story generation request stays pending for an extended period
- **THEN** the dashboard SHALL continue showing which draft is still generating
- **AND** the state copy SHALL make it clear that generation is still in progress rather than silently failing

#### Scenario: Failure state suggests recovery
- **WHEN** a generation request fails because of timeout, network interruption, or backend failure
- **THEN** the dashboard SHALL show an explicit failure message for that request
- **AND** the user SHALL be able to retry without refreshing the whole bookshelf page

### Requirement: The dashboard SHALL let users express custom story intent beyond the opening
The free-creation area SHALL provide an additional optional input for style, tone, or desired story direction so users can constrain the generated experience without overloading the opening text itself.

#### Scenario: User adds style guidance before generation
- **WHEN** a user prepares a free-creation request
- **THEN** the bookshelf composer SHALL offer an optional field for guidance such as genre, emotional tone, or expected direction
- **AND** leaving that field empty SHALL still keep the current quick-start flow available
