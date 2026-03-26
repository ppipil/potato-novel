## ADDED Requirements

### Requirement: Active story progression SHALL be local after package load
Once an interactive story package has been loaded into the active story experience, the frontend SHALL advance the story using local package data only and MUST NOT require additional SecondMe requests for intermediate turns.

#### Scenario: Choice click advances immediately
- **WHEN** the player clicks one of the available choices in a loaded package
- **THEN** the next node is shown from local package data without waiting for a new SecondMe continuation response

#### Scenario: Mid-story network generation is not required
- **WHEN** the player progresses between non-ending nodes of a loaded package
- **THEN** the system does not call SecondMe to generate another turn before rendering the next scene

### Requirement: Local playback SHALL update structured relationship and persona state
Each choice in a playable node MUST expose structured state impact data, and the active story experience SHALL apply those deltas locally as the player advances through the package.

#### Scenario: Choosing an option updates local state
- **WHEN** the player selects a choice with relationship or persona impact values
- **THEN** the active story state immediately reflects those updated values before the next choice is presented

#### Scenario: Ending state reflects the chosen path
- **WHEN** the player reaches an ending node
- **THEN** the local final state represents the cumulative impacts from the path the player actually selected

### Requirement: Active story input SHALL be limited to packaged choices
The active story experience SHALL present only the packaged choice buttons during a run and MUST NOT offer custom free-text actions while this change is active.

#### Scenario: Custom action box is removed
- **WHEN** the player is reading a pre-generated story package
- **THEN** the interface shows only structured package choices and no custom input field for open-ended actions

#### Scenario: Choice set remains exactly three during playable turns
- **WHEN** the current node is a playable turn
- **THEN** the interface presents exactly three packaged options for that turn

### Requirement: The system SHALL support at least one local ending path per package
Each package MUST provide at least one reachable ending node, and the active story experience SHALL recognize story completion locally when the current node is an ending node.

#### Scenario: Ending node completes the run locally
- **WHEN** the player advances into an ending node
- **THEN** the story run is marked complete without requesting an additional continuation turn

#### Scenario: Completed run can be finalized into a saved story artifact
- **WHEN** a local run has reached an ending node
- **THEN** the system can compile the selected path into a saved story record for bookshelf/history review
