## 1. Backend Story Session Foundation

- [x] 1.1 Define and persist an interactive story session model with `session_id`, history, current turn payload, and lightweight state fields.
- [x] 1.2 Add backend endpoints to start a story session, continue a session with user input, fetch an existing session, and finalize a session into a saved story artifact.
- [x] 1.3 Update prompt construction and response normalization so each turn returns structured paragraphs, exactly three differentiated choices, and updated state.
- [x] 1.4 Add server-side guards for authenticated session ownership, invalid continuation input, and bounded recent-history context trimming.

## 2. Frontend Interactive Fiction Experience

- [x] 2.1 Update the story-entry flow so starting a story opens an interactive session instead of generating a full story page.
- [x] 2.2 Implement tap-to-continue paragraph reveal with local `current_index` tracking and delayed choice display until the current turn is fully revealed.
- [x] 2.3 Support both predefined choice submission and custom user action submission for continuing a story turn.
- [x] 2.4 Update finalization and history views so a completed interactive session can be saved and reviewed with session metadata.

## 3. State, Branching, And Narrative Quality

- [x] 3.1 Implement explicit stage progression across `opening`, `conflict`, `climax`, and `ending` in the stored story state.
- [x] 3.2 Track flags and relationship values that can influence later turn generation and ending outcomes.
- [x] 3.3 Enforce differentiated-option rules in prompts and fallback handling so each turn presents materially distinct dramatic strategies.
- [x] 3.4 Add a lightweight reversal hook so ending turns can reflect earlier trust, suspicion, or manipulation choices.

## 4. SecondMe Persona Integration

- [x] 4.1 Define how current SecondMe user data can optionally map into advisory persona signals for story interaction.
- [x] 4.2 Add frontend presentation for a recommended or highlighted persona-aligned choice without restricting user freedom.
- [x] 4.3 Add an "AI would choose" comparison surface that records the user choice independently from the AI recommendation.

## 5. Validation

- [ ] 5.1 Run a local authenticated smoke test covering login, story start, at least three continuations, finalization, and history review.
- [ ] 5.2 Verify paragraph reveal behavior, choice gating, and custom action submission in the browser UI.
- [x] 5.3 Capture any remaining gaps for post-MVP work, especially multi-AI roleplay orchestration and AI path playback.
