## CHANGED Requirements

### Requirement: The interactive story page SHALL prioritize literary reading presentation
The active story page SHALL remain reading-first while using compact interaction chrome, so story prose stays dominant but action components no longer consume most of the viewport.

#### Scenario: Choice dock remains compact yet tappable
- **WHEN** a turn finishes revealing and options appear
- **THEN** all three options fit within the bottom region without visually taking over the entire screen
- **AND** each option remains easy to tap on mobile

### Requirement: Top bar preserves story context without harming legibility
The top header SHALL keep a frosted/translucent aesthetic, but MUST include sufficient blur and contrast-safe background opacity to prevent text overlap artifacts from scrolled content.

#### Scenario: Header title stays readable while scrolling
- **WHEN** long story text passes under the sticky header
- **THEN** the title and actions remain clearly legible without background text ghosting

### Requirement: Story progression SHALL keep scroll position reliable
The interactive page SHALL auto-scroll predictably whenever new node content, reveal progress, or option availability updates the bottom of the reading flow.

#### Scenario: Repeated choice progression always re-anchors to newest content
- **WHEN** the user advances through multiple consecutive turns
- **THEN** the viewport follows newly appended story content without requiring manual repeated scrolling

### Requirement: Situation notes SHALL remain contextual to the active turn
`directorNote` content SHALL be presented as context for the current node and SHOULD NOT accumulate as repeated historical blocks that dominate the transcript.

#### Scenario: Situation note updates with current node only
- **WHEN** the user moves to a new story node
- **THEN** the displayed situation note reflects the current node context
- **AND** older notes do not keep stacking as persistent scrolling clutter
