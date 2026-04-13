## CHANGED Requirements

### Requirement: The dashboard SHALL collect custom-story style through a single-select tag
The free-creation area SHALL present style control as a single-select tag set rather than a freeform style field, so users can express intent with low cognitive load and the backend can map the choice to a stable generation strategy.

#### Scenario: User selects one primary style before generation
- **WHEN** a user prepares a custom story from the bookshelf dashboard
- **THEN** the composer SHALL offer exactly one primary style selection from `言情`、`悬疑`、`恐怖`、`搞笑`
- **AND** the current request SHALL not proceed without one selected style

#### Scenario: Optional note remains secondary
- **WHEN** a user wants to add more context beyond the selected style
- **THEN** the dashboard SHALL provide one optional short note field for supplemental constraints
- **AND** the UI SHALL frame that field as additional guidance rather than the main style control
