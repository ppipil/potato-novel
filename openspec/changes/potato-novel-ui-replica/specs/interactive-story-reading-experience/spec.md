## ADDED Requirements

### Requirement: The interactive story page SHALL prioritize literary reading presentation
The active co-creation page SHALL present the story as a single vertical reading flow with a frosted top bar, large serif prose, generous line height, and extended bottom padding so the narrative remains the visual focus above the bottom action dock.

#### Scenario: Story prose remains readable above the footer
- **WHEN** a turn with multiple paragraphs is displayed on the interactive page
- **THEN** the prose is rendered in a reading-first column with enough bottom padding that the final visible paragraph is not obscured by the bottom action area

#### Scenario: Top bar preserves story context without dominating the page
- **WHEN** the interactive page is displayed
- **THEN** the page shows a frosted header with a back action, truncated story title, and a lightweight save affordance

### Requirement: AI-generated story content SHALL render as unboxed serif narrative blocks
System-generated story paragraphs SHALL appear without a filled speech-bubble container, using serif typography, enlarged text size, long line height, and first-line indentation to simulate literary reading rather than chat UI.

#### Scenario: Story paragraphs look like narrative prose
- **WHEN** AI-generated content is rendered in the story flow
- **THEN** each paragraph appears as plain narrative text with serif styling and first-line indentation instead of a chat bubble card

#### Scenario: Newly inserted narrative content animates into place
- **WHEN** a new story turn is added after the user continues the session
- **THEN** the new prose block enters with the shared chunk-in animation

### Requirement: User-submitted actions SHALL render as right-aligned paper bubbles during active play
On the active co-creation page, previously submitted user actions SHALL render as right-aligned action bubbles with a paper-200 background, asymmetrical rounding, sans-serif text, and a visible colored "我：" prefix to distinguish the player voice from the narrative voice.

#### Scenario: Prior user action is visually distinct from prose
- **WHEN** the transcript includes a user action in the active session view
- **THEN** that entry appears right-aligned and uses bubble styling rather than the same typography as narrative prose

#### Scenario: User label is explicit
- **WHEN** a user action bubble is rendered
- **THEN** the bubble visibly prefixes the action text with a styled first-person label

### Requirement: The bottom action region SHALL use a frosted glass dock with recommended actions and custom input
The interactive story page SHALL anchor its action region to the bottom of the viewport, render it with a strong frosted glass treatment, show vertically stacked recommendation buttons, and provide a pill-shaped custom input row whose submit affordance changes based on whether custom text exists.

#### Scenario: Recommended actions appear as stacked tactile buttons
- **WHEN** the current story turn is ready for user action
- **THEN** the interface shows the recommended actions as vertically stacked white cards with card shadow and pressed-state feedback

#### Scenario: Custom input affordance changes with content state
- **WHEN** the custom action input is empty
- **THEN** the trailing action presents the "强制结局" style fallback action instead of a highlighted send arrow

#### Scenario: Custom input affordance promotes sending when text is present
- **WHEN** the custom action input contains text
- **THEN** the trailing action changes into an accent-colored send control for submitting that text

### Requirement: Loading and reveal states SHALL match the supplied motion language
The interactive story page SHALL use three-dot typing feedback while waiting for the next turn, SHALL animate the bottom dock with slide-up motion when it becomes available, and SHALL preserve the existing paragraph-reveal gating before choices become actionable.

#### Scenario: Waiting state uses animated typing dots
- **WHEN** the frontend is waiting for the backend to return the next story turn
- **THEN** the page shows a three-dot animated typing indicator that scales and fades in a staggered wave

#### Scenario: Action dock appears after reveal completion
- **WHEN** the current turn's paragraphs have been fully revealed and the choice area becomes available
- **THEN** the bottom action region enters with a slide-up transition instead of appearing abruptly
