## ADDED Requirements

### Requirement: Story sessions SHALL support multi-turn continuation
The system SHALL create a durable story session for each new interactive story and SHALL allow authenticated users to continue that session across at least three turns before finalization. Each continuation response MUST be based on the stored session history, current story state, and the user's selected or custom action.

#### Scenario: Start a new story session
- **WHEN** an authenticated user starts an interactive story with an opening and role
- **THEN** the system returns a new `session_id`, the first turn payload, and initialized story state for that session

#### Scenario: Continue a session with a user action
- **WHEN** an authenticated user submits a choice or custom input to continue an existing session
- **THEN** the system returns the next turn payload generated from the stored session history, current state, and submitted action

#### Scenario: Resume a previously created session
- **WHEN** an authenticated user requests an existing story session they own
- **THEN** the system returns the latest persisted turn payload, story history summary, and current state for that session

### Requirement: Story state SHALL be explicit and stage-aware
The system SHALL persist structured story state for each session, including `stage`, `flags`, `relationship`, and `turn`. The state model MUST support progression through `opening`, `conflict`, `climax`, and `ending` phases and SHALL be updated on each turn.

#### Scenario: State advances with story progression
- **WHEN** a user continues a story session
- **THEN** the returned session state includes an updated turn count and any changed stage, flags, or relationship values

#### Scenario: Ending logic uses accumulated state
- **WHEN** a session reaches the ending stage
- **THEN** the system uses stored flags and relationship values to influence the ending outcome or reversal

### Requirement: Finalized stories SHALL compile session history into a readable story record
The system SHALL support finalizing a story session into a complete story artifact that can be saved and viewed later. The compiled story MUST preserve the original opening, major turn beats, and ending summary from the session.

#### Scenario: Finalize an interactive story
- **WHEN** an authenticated user finalizes a story session
- **THEN** the system returns a complete story artifact suitable for saving in story history

#### Scenario: Save a finalized story with session metadata
- **WHEN** a finalized story is saved
- **THEN** the saved record includes session-linked metadata such as role, opening, turn count, and session identifier

### Requirement: Choice generation SHALL produce differentiated dramatic strategies
Each story turn MUST provide exactly three options. The options SHALL differ in motive, behavioral style, and likely narrative consequence so the user is choosing among distinct strategies rather than paraphrases.

#### Scenario: Distinct motives and styles per turn
- **WHEN** the system returns choices for a story turn
- **THEN** the three choices represent materially different strategies such as confrontation, manipulation, avoidance, trust, sacrifice, or deception

#### Scenario: Choices imply divergent consequences
- **WHEN** the user compares the three choices in a turn
- **THEN** each choice suggests a different likely relationship change, triggered event, or story risk

### Requirement: Story context SHALL be bounded for continuation prompts
The system SHALL preserve recent turn history and current summarized state when generating a continuation, and it MUST trim older raw turn details once the retained context limit is exceeded.

#### Scenario: Continue a long-running session
- **WHEN** a session exceeds the retained recent-history limit
- **THEN** the system uses current state plus the retained recent turns instead of the full raw transcript to generate the next turn
