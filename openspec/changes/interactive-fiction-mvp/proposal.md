## Why

The current Potato Novel demo still behaves like a single-shot story generator: users choose an opening and role, then receive a full story at once. To reach the intended "AI-powered visual novel" experience, we need a first-class interactive fiction loop where users advance the story turn by turn, choose materially different actions, and see the narrative respond to those choices.

## What Changes

- Introduce a session-backed interactive story loop so a story can be created, resumed, advanced across multiple turns, and finalized into a complete record.
- Replace full-page story dumping with tap-to-continue paragraph presentation, where only one paragraph is revealed at a time before choices appear.
- Define differentiated choice generation requirements so each turn presents three dramatically distinct options with different motives, styles, and downstream effects.
- Add lightweight story state tracking for stage progression, flags, relationships, and turn count to steer branching and reversals.
- Define how SecondMe persona signals can influence option recommendation and provide a visible "AI would choose" comparison experience without restricting user freedom.

## Capabilities

### New Capabilities
- `interactive-story-session`: Covers multi-turn session lifecycle, turn advancement, state tracking, branching inputs, and final story compilation.
- `tap-to-continue-story`: Covers segmented paragraph presentation, click-to-reveal behavior, and choice-node gating in the frontend experience.
- `secondme-story-persona`: Covers implicit persona-based recommendation, AI choice comparison, and extensible support for AI path playback.

### Modified Capabilities

## Impact

- Affects backend story endpoints and session persistence in [backend/app/main.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/main.py).
- Affects frontend bookshelf, story interaction, and history views in [frontend/src/views/BookshelfPage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/BookshelfPage.vue), [frontend/src/views/StoryResultPage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/StoryResultPage.vue), and [frontend/src/views/StoryHistoryPage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/StoryHistoryPage.vue).
- Affects frontend API bindings in [frontend/src/lib/api.js](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/lib/api.js) and interaction styling in [frontend/src/styles.css](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/styles.css).
- Introduces new spec coverage for session contracts, interaction UX, and SecondMe persona-driven recommendation behavior.
