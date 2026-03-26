## Context

The repository already has a Vue 3 frontend and FastAPI backend that support SecondMe login, opening selection, role selection, one-shot story generation, and local story saving. The new product direction changes the interaction model from "generate a whole story page" to "advance a branching story session turn by turn," while preserving the current authentication and local persistence model.

This change cuts across backend APIs, prompt shaping, session storage, and frontend rendering. It also introduces a lightweight state machine and a presentation pattern where paragraph reveal and choice gating become first-class UX behaviors. SecondMe persona influence is desirable, but for MVP it must remain advisory rather than access-controlling.

## Goals / Non-Goals

**Goals:**
- Define an MVP architecture for session-backed, multi-turn interactive fiction.
- Support turn-by-turn story continuation with structured backend responses and recoverable session state.
- Support tap-to-continue paragraph reveal so story text is consumed incrementally before users choose the next action.
- Require three materially differentiated options per turn, driven by motive, style, and likely consequences.
- Introduce lightweight story state that can steer stage progression, relationships, and reversal setup.
- Define a low-risk integration point for SecondMe persona recommendation and AI-vs-user choice comparison.

**Non-Goals:**
- Building a full branching-engine authoring system with deterministic handcrafted story graphs.
- Implementing fully autonomous multi-AI dialogue orchestration as part of MVP.
- Replacing the current OAuth flow, storage strategy, or deployment architecture.
- Using persona inference to lock or remove user choices.

## Decisions

### Use a session-backed interaction model instead of one-shot story generation
The backend will represent each story as a session with `session_id`, recent history, current state, and current turn payload. Each continuation request appends the user's action, advances state, and returns the next structured story fragment.

Alternative considered: keep generating whole-story text and simulate turns only in the frontend. We are not choosing that because it breaks persistence, branching continuity, and server-side state steering.

### Standardize turn responses as structured narrative payloads
Each story turn will return a structured object containing segmented paragraphs, three differentiated choices, and updated story state. This keeps frontend rendering simple and makes turn semantics testable.

Alternative considered: return plain freeform text and let the frontend heuristically split paragraphs or infer choices. We are not choosing that because it would make reveal behavior fragile and blur the contract between narrative generation and UI interaction.

### Keep story state lightweight and explicit
The state model will include stage, flags, relationship values, and turn count. This is enough to drive opening/conflict/climax/ending flow, support simple reversals, and remain inspectable in persisted sessions.

Alternative considered: store only narrative text history and let the model infer everything implicitly. We are not choosing that because explicit state is needed for branching consistency, recommendation logic, and future debugging.

### Separate story presentation from story generation
The frontend will own paragraph reveal state such as `current_index`, while the backend will own generated paragraph content, choices, and durable session state. This prevents transient UI state from polluting persisted story logic.

Alternative considered: persist paragraph reveal position in the backend. We are not choosing that for MVP because reveal state is a local presentation concern and does not affect narrative correctness.

### Treat differentiated choices as a hard content contract
Each turn must yield exactly three options with distinct motive, style, and likely consequences. Prompting and response validation should enforce this because choice quality is core product value, not polish.

Alternative considered: treat option diversity as best effort. We are not choosing that because weakly differentiated choices directly collapse the "interactive fiction" experience.

### Make SecondMe persona influence advisory
Persona signals from SecondMe will be used to rank, highlight, or annotate choices and to show an "AI would choose" comparison. Users remain free to choose any option or input custom actions.

Alternative considered: constrain available branches based on persona. We are not choosing that because the PRD calls for recommendation, not restriction, and hard gating would reduce user agency.

## Risks / Trade-offs

- [Model output may fail to keep choices meaningfully distinct] -> Mitigation: define explicit spec requirements for motive/style/consequence differences and validate minimum structure server-side.
- [State drift may appear across long sessions] -> Mitigation: persist explicit state fields and trim prompt history to recent turns plus summarized state.
- [Paragraph splitting quality may vary by model output] -> Mitigation: require backend responses to return segmented paragraphs rather than relying on frontend text splitting.
- [SecondMe persona data may be incomplete or unavailable] -> Mitigation: treat persona recommendation as optional enhancement with neutral fallback behavior.
- [Current local JSON persistence is not multi-user robust] -> Mitigation: keep JSON storage for MVP and document richer persistence as follow-up work, not hidden complexity.

## Migration Plan

1. Add session-based story endpoints while keeping legacy generation routes temporarily compatible or aliasing to the new entrypoint.
2. Update the frontend story page to consume session responses and render paragraph-reveal interaction.
3. Preserve existing local story-saving behavior by compiling finalized sessions into a saved story artifact.
4. Validate authenticated flow end-to-end from login through story start, continuation, finalization, and history review.

## Open Questions

- How exactly will SecondMe persona attributes be exposed to the backend in the current integration flow: explicit user info fields, implicit route metadata, or future profile enrichment?
- Should "AI would choose" be generated live per turn or precomputed alongside the user-facing choices for consistency?
- For post-MVP multi-AI roleplay, should narrator and character turns be separate generation passes or one structured response containing multiple voices?

## Post-MVP Follow-Ups

- Multi-AI roleplay orchestration between narrator, character A, and character B remains a follow-up rather than part of the MVP loop.
- Alternative AI path playback is only scaffolded through session structure today and still needs a dedicated persistence and replay design.
- Local JSON persistence is sufficient for prototype sessions but should move to a more robust store before multi-user or long-lived deployment.
