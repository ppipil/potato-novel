## ADDED Requirements

### Requirement: AI persona guidance SHALL evaluate choices without regenerating the whole story
The system SHALL support lightweight SecondMe-powered persona guidance during story play. This guidance SHALL evaluate the current choice set and user persona context without regenerating the full story package.

#### Scenario: Requesting a choice recommendation
- **WHEN** a user asks for AI persona guidance on a story node with available choices
- **THEN** the system sends the current node context, available options, and user persona context to the guidance backend
- **AND** the response does not require creating a new story skeleton or rewriting the story package

### Requirement: AI persona guidance SHALL return interpretable recommendations
The system SHALL return an explicit recommendation payload that can explain how the user’s AI persona would likely respond in the current scene.

#### Scenario: Showing a recommended choice
- **WHEN** persona guidance succeeds for a node
- **THEN** the response includes a recommended choice identifier or equivalent option match
- **AND** the response includes explanatory text that can be shown to the user

#### Scenario: Preserving user agency
- **WHEN** persona guidance is displayed
- **THEN** the user may still choose any available option
- **AND** the system does not automatically execute the recommendation on the user’s behalf

### Requirement: AI persona guidance SHALL coexist with ending interpretation
The system SHALL allow persona guidance during play and interpretive features such as ending analysis or epilogue generation after play without conflating the two flows.

#### Scenario: Ending interpretation after guided play
- **WHEN** a user finishes a story after using persona guidance during earlier turns
- **THEN** the user may still request ending analysis or epilogue text
- **AND** ending interpretation remains a separate request from in-story choice recommendation
