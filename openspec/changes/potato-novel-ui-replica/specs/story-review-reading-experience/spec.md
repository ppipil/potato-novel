## ADDED Requirements

### Requirement: The saved-story review page SHALL reuse the literary reading shell without editable controls
The read-only review page SHALL reuse the same paper reading shell, serif narrative presentation, and centered mobile composition as the interactive page, but SHALL omit the bottom input dock and any controls that imply the story can still be continued.

#### Scenario: Review mode removes active input affordances
- **WHEN** a saved story is opened in the review page
- **THEN** the page displays the story content without custom input controls or recommended action buttons

#### Scenario: Review mode keeps the literary reading style
- **WHEN** the saved story is displayed
- **THEN** the story body uses the same reading-first serif presentation as the interactive experience

### Requirement: Review mode SHALL render user actions as centered divider labels
In the read-only review page, user-selected actions SHALL render as centered labels with border and rounded corners, with a dashed horizontal divider extending through the row, instead of the right-aligned active-play bubble styling.

#### Scenario: Review entries distinguish player actions from narration
- **WHEN** the displayed story timeline includes a user action
- **THEN** that action is rendered in a centered divider treatment rather than as continuous prose

#### Scenario: Divider treatment remains readable inside long timelines
- **WHEN** multiple user actions appear across a saved story
- **THEN** each action label remains visually separated from surrounding narrative blocks by the dashed divider structure

### Requirement: The review page SHALL preserve story identity and navigation context
The review page SHALL show a centered story title and provide a clear return path to the bookshelf or history list without breaking the quiet reading atmosphere.

#### Scenario: Reader sees story identity immediately
- **WHEN** the review page loads a saved story
- **THEN** the story title is displayed prominently near the top of the reading view

#### Scenario: Reader can leave review mode
- **WHEN** the user wants to exit the review page
- **THEN** the page provides a clear navigation action back to the broader bookshelf or history flow
