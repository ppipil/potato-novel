## CHANGED Requirements

### Requirement: Story progression SHALL keep scroll position reliable
The interactive page SHALL reveal each turn in a stable two-step rhythm: the current node's prose must finish presenting before the option dock becomes interactable or auto-scroll re-anchors to the choices.

#### Scenario: Final paragraph is not skipped by choice reveal
- **WHEN** the current turn still has an unrevealed final paragraph
- **THEN** the page SHALL keep the viewport anchored to prose reveal rather than jumping focus to the option dock
- **AND** choices SHALL remain non-interactable until the node prose has fully revealed

#### Scenario: Options appear after prose settles
- **WHEN** the user reveals the last paragraph of the current node
- **THEN** the option area SHALL appear only after that final paragraph is visible
- **AND** any follow-up auto-scroll to the choice dock SHALL happen after the prose reveal step completes

### Requirement: The interactive story page SHALL preserve readable paragraph integrity
The active story page SHALL present paragraph breaks that preserve narrative coherence, including quoted dialogue and tightly coupled sentence groups, rather than fragmenting text on every sentence-ending period.

#### Scenario: Quoted dialogue remains in one paragraph
- **WHEN** a generated scene contains consecutive quoted lines or quoted text followed by its immediate narrative beat
- **THEN** the displayed paragraph segmentation SHALL avoid splitting the content into awkward micro-paragraphs inside the same quoted beat

#### Scenario: Explicit model line breaks are preserved
- **WHEN** the generated scene already includes explicit newline-based paragraph breaks
- **THEN** the reading experience SHALL preserve those paragraph boundaries in the rendered `paragraphs` output
