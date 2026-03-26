## ADDED Requirements

### Requirement: Story text SHALL be revealed one paragraph at a time
The interactive story interface SHALL present generated story content as an ordered list of paragraphs and SHALL reveal only one paragraph at a time during active reading.

#### Scenario: Initial paragraph display
- **WHEN** the frontend receives a new turn payload with multiple paragraphs
- **THEN** it displays only the first paragraph and stores reveal progress locally

#### Scenario: Reveal the next paragraph on tap
- **WHEN** the user taps the story area before the current turn is fully revealed
- **THEN** the interface displays the next paragraph in sequence

### Requirement: Choice presentation SHALL wait until the current turn is fully revealed
The interface MUST NOT present the turn's choice buttons until all paragraphs in the current turn have been revealed.

#### Scenario: Choices remain hidden during partial reveal
- **WHEN** one or more paragraphs in the current turn are still hidden
- **THEN** the choice area remains unavailable or disabled

#### Scenario: Choices appear after final paragraph
- **WHEN** the user reveals the final paragraph of the current turn
- **THEN** the interface displays the available choices and custom input controls for the next action

### Requirement: Reveal progress SHALL reset for each new turn
The frontend SHALL reset local paragraph reveal progress whenever a new turn payload arrives from the backend.

#### Scenario: New turn starts from first paragraph
- **WHEN** the system returns a continuation response for the next story turn
- **THEN** the interface resets paragraph reveal index to the first paragraph of the new turn

### Requirement: The interaction UI SHALL support both button choices and custom input
The interface SHALL allow the user to continue the story by selecting one of the provided choices or by entering a custom action once the current turn is fully revealed.

#### Scenario: Submit a predefined choice
- **WHEN** the current turn is fully revealed and the user clicks a provided choice
- **THEN** the interface submits that choice as the next story action

#### Scenario: Submit a custom action
- **WHEN** the current turn is fully revealed and the user enters a custom action
- **THEN** the interface submits the custom action as the next story action
