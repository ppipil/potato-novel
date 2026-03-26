## Context

The current implementation creates a session on story start, stores the latest generated turn on the backend, and calls SecondMe again on every `/api/story/continue` request. The story page also supports custom free-text actions, which fits a chat-style improvisation loop but conflicts with the target experience of a preload-first interactive novel.

This change moves the product toward a "story package" model: the backend asks SecondMe for a complete branching bundle up front, the bookshelf can warm that bundle before the user opens it, the story page plays the bundle locally without additional turn requests, and SecondMe is called again only after an ending is reached. The current OAuth/session boundary stays unchanged, and package ownership remains tied to the authenticated backend session.

## Goals / Non-Goals

**Goals:**
- Define a package format that can represent a complete 4-6 turn interactive story with branching nodes and at least one ending.
- Support proactive package generation from the bookshelf so story entry is usually immediate.
- Ensure in-story choice selection is local-only: instant next-node display, local state updates, and no mid-story SecondMe call.
- Support explicit regeneration when the user wants a different package for the same opening.
- Define a post-ending analysis step with stable output fields for persona labels, romance commentary, life commentary, and next-universe recommendation.

**Non-Goals:**
- Building a general authoring platform for arbitrary long-form branching fiction.
- Supporting open-ended custom actions during active play in this change.
- Reworking OAuth, user identity, or deployment topology.
- Guaranteeing zero wait in every case; the requirement is to preload opportunistically and reuse a ready package whenever possible.

## Decisions

### Generate complete story packages instead of per-turn continuations
The backend will request a full branching package from SecondMe in one generation step and persist it as the playable unit. A package will contain package metadata, node graph data, playable node order/links, per-choice impact, and one or more ending nodes.

Alternative considered: continue storing only the latest turn and request the next turn lazily. We are not choosing that because it preserves the current wait-on-every-choice behavior and prevents truly local playback.

### Treat bookshelf preload as a best-effort prewarm tied to opening and role
When the user is on the bookshelf and has a concrete opening/role candidate, the frontend may ask the backend to generate a package before story entry. The backend will reuse a ready non-consumed package for the same opening/role/user when possible; if the user explicitly chooses "generate new", the backend will create a fresh package and mark the prior draft as superseded.

Alternative considered: generate only after the user enters the story page. We are not choosing that because it keeps the most noticeable wait at the exact moment the user expects to start reading.

### Use an explicit node-graph contract with local state deltas
Each playable node will contain prose content, exactly three choices, and links to subsequent nodes or ending nodes. Each choice will also declare structured effects, including persona or relationship deltas, so the frontend can update visible state locally without interpreting freeform prose.

Alternative considered: encode impacts only inside narrative text and let the frontend infer them. We are not choosing that because local-only playback needs deterministic, inspectable state transitions.

### Keep runtime progression state on the client and durable package state on the backend
The backend will persist the generated package and package metadata, while the frontend will own transient runtime state such as current node id, visited path, current relationship/persona totals, and reveal progress. Completion can be saved back to the backend when the story reaches an ending or when the user saves the artifact.

Alternative considered: POST every choice to the backend only for persistence, even if no new generation occurs. We are not choosing that for MVP because the product requirement is to make in-story progression feel immediate and local.

### Temporarily remove custom input from active play
The active story page will present only structured choices from the package and will not offer a free-text action box. This preserves branch validity and avoids requiring fallback generation mid-run.

Alternative considered: keep custom input as an escape hatch that triggers live generation. We are not choosing that because it reintroduces the chat pattern and breaks the predictability of a pre-generated branch bundle.

### Generate the ending analysis only after the player reaches an ending node
Once local playback reaches an ending node, the frontend or backend will assemble the opening, chosen path, ending summary, and final state into a single SecondMe analysis request. The normalized response must include potato persona labels, romance-oriented analysis, life-style commentary, and a next-universe recommendation hook.

Alternative considered: pre-generate the ending analysis together with the story package. We are not choosing that because the chosen branch and resulting state are not known until runtime.

## Risks / Trade-offs

- [A single generation may produce an invalid or shallow branch graph] -> Mitigation: validate the package shape server-side before marking it ready, including turn count, ending-node presence, three choices per playable node, and valid next-node references.
- [Bookshelf preload may generate packages the user never reads] -> Mitigation: keep only a small number of draft packages per user/opening and allow superseding or expiring stale unused drafts.
- [Local-only progression may make resume behavior less robust if the tab closes mid-run] -> Mitigation: persist lightweight runtime progress in session storage first and save completed stories back to the backend at ending/finalization.
- [Package generation latency may still be visible when preload misses] -> Mitigation: surface readiness state in the bookshelf and start prewarm as early as enough input is available.
- [Frontend and backend state math could diverge] -> Mitigation: use structured choice delta fields and centralize package normalization in the backend.

## Migration Plan

1. Add package-oriented backend endpoints and persistence alongside the current session flow.
2. Update the bookshelf to request package prewarm and surface ready/regenerating states.
3. Update the story page to consume a generated package and advance locally without `/api/story/continue`.
4. Disable custom input on the story page and switch save/finalize behavior to compile from the local chosen path.
5. Keep ending analysis on the existing post-story step, but update the prompt/input contract to use the completed path from the package.
6. Remove or de-emphasize legacy per-turn continuation once the package flow is verified end to end.

## Open Questions

- Should the bookshelf preload only the currently selected opening/role, or may it also prewarm one recommended opening in the background?
- Should an already-opened but unfinished package be resumable from local storage only, or should completion progress be written back to the backend for cross-device continuity?
- How many superseded draft packages per opening should be retained before cleanup to balance freshness and storage simplicity?
