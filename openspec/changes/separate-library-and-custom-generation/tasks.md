## 1. Data and Story Source Modeling

- [ ] 1.1 Add a persistent source marker for story packages so the backend can distinguish fixed library packages from custom-generated packages.
- [ ] 1.2 Define the database read path for fixed library stories and verify the backend can return a stored package without invoking generation.
- [ ] 1.3 Prepare a minimal seed or import workflow for at least one library story package to validate the new model end to end.

## 2. Library Loading Flow

- [ ] 2.1 Replace the current template preload entry path so library stories load stored packages instead of calling the runtime generation flow.
- [ ] 2.2 Update bookshelf card states and wording from download/pre-cache semantics to loading/entering semantics for library stories.
- [ ] 2.3 Remove or adapt legacy library-only preload state handling that assumes every template story needs per-user generation.

## 3. Custom Story Generation Flow

- [ ] 3.1 Separate the custom creation entry path from library loading so freeform openings always start the runtime generation workflow.
- [ ] 3.2 Introduce explicit generation phases for custom stories, including skeleton, opening, first-branch, and ready-to-enter.
- [ ] 3.3 Update the custom creation UI to show phase-based progress and an approximate wait expectation.
- [ ] 3.4 Allow the reader to enter a custom story once the opening slice is ready while later nodes continue hydrating in the background.

## 4. AI Persona Guidance

- [ ] 4.1 Add a backend endpoint contract for lightweight persona guidance using the current node context and available choices.
- [ ] 4.2 Update the reading UI to request persona guidance without blocking manual choice selection.
- [ ] 4.3 Define how persona guidance output is rendered, including recommendation text and explanation while preserving user agency.

## 5. Validation and Migration

- [ ] 5.1 Verify that library stories no longer invoke story package generation during normal entry.
- [ ] 5.2 Verify that custom story generation still produces playable sessions and that its phases remain understandable to users.
- [ ] 5.3 Verify that saved stories, history playback, and ending interpretation continue to work across both story sources.
