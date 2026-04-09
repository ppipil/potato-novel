## CHANGED Requirements

### Requirement: The dashboard SHALL render recommended openings as scannable stacked template cards
The bookshelf dashboard SHALL keep recommended openings in a vertically stacked format, but card density MUST support quick scanning on mobile without requiring excessive scroll per item.

#### Scenario: Template cards do not dominate the first screen
- **WHEN** the bookshelf renders multiple recommended openings
- **THEN** at least two full cards can be scanned within one typical mobile viewport section
- **AND** each card keeps visible genre, title, and summary hierarchy without oversized spacing

### Requirement: The dashboard SHALL support non-blocking generation waiting
When users start a story that may require long generation, the bookshelf experience SHALL provide visible progress/waiting state without hard-locking the whole page.

#### Scenario: Long generation does not freeze all interactions
- **WHEN** a story generation request remains pending
- **THEN** the user can continue browsing bookshelf content
- **AND** the UI clearly indicates which story action is currently generating

#### Scenario: Pending generation state remains understandable
- **WHEN** the user leaves and returns focus during a pending generation
- **THEN** the dashboard still shows a recoverable state label and next action
