## ADDED Requirements

### Requirement: Custom node generation SHALL follow prose-before-choice order
For each turn node in a custom story package, the system MUST generate node prose first, then generate that node's choices using the generated prose as required context.

#### Scenario: Generating a turn node
- **WHEN** the backend prepares a custom story turn node
- **THEN** it first generates the node scene/paragraph content
- **AND** it generates the node choices only after prose is available for that same node

#### Scenario: Choice prompt references generated prose
- **WHEN** the choice-generation step runs for a node
- **THEN** the prompt includes the generated prose and node summary context
- **AND** returned choices align with the actual dramatic content of that node

### Requirement: Custom package hydration SHALL iterate per node in reading order
The custom-story hydration pipeline MUST process turn nodes in a deterministic reading order and complete each node's prose-and-choice pair before moving to the next node.

#### Scenario: Hydrating all nodes
- **WHEN** the backend performs custom package hydration
- **THEN** it iterates turn nodes in reading order
- **AND** each node transitions through `prose-ready` then `choices-ready` before the next node starts
