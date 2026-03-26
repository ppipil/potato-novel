## Why

The current Potato Novel interaction loop still waits on SecondMe for every story turn, which makes entry and progression feel like chat generation instead of an interactive novel. We need to shift the experience toward a preload-first story package so bookshelf browsing can warm up playable content and in-story choices feel instant.

## What Changes

- Introduce pre-generated interactive story packages that contain a full 4-6 turn branching bundle, including narrative nodes, exactly three choices per playable turn, per-choice state impact, next-node links, and at least one ending node.
- Allow the bookshelf experience to proactively request and cache a story package before the user opens the story so entering a selected story can usually begin immediately.
- Replace per-turn SecondMe continuation calls with local story package playback: after a package is loaded, the frontend advances nodes, reveals text, and updates relationship/persona state without additional mid-story requests.
- Add an explicit "generate new" flow so users can discard the current pre-generated package for an opening and request a fresh bundle before reading.
- Restrict the active story experience to structured choices only by temporarily removing custom free-text actions that would break the pre-generated branch graph.
- Keep SecondMe involved only at package-generation time and once more after the player reaches an ending, where it produces a closing analysis with potato persona labels, romance commentary, life commentary, and a next-universe recommendation.

## Capabilities

### New Capabilities
- `story-pack-preloading`: Covers bookshelf-triggered package generation, package readiness state, entry-time reuse, and explicit regeneration of a fresh package.
- `local-story-pack-playback`: Covers the local node graph contract, instant choice-based advancement, local relationship/persona updates, and removal of custom input during active play.
- `secondme-ending-analysis-summary`: Covers post-ending summary generation, required analysis fields, and recommendation output after a local story package reaches an ending.

### Modified Capabilities

## Impact

- Affects backend story orchestration, package persistence, and ending-analysis prompts in [backend/app/main.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/main.py).
- Likely affects story session/package storage in [backend/data/story_sessions.json](/Users/pipilu/Documents/Projects/potato-novel/backend/data/story_sessions.json) or its replacement structure.
- Affects bookshelf preload and story entry behavior in [frontend/src/views/BookshelfPage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/BookshelfPage.vue).
- Affects active reading/playback behavior in [frontend/src/views/StoryResultPage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/StoryResultPage.vue).
- Affects saved-story and ending-analysis display behavior in [frontend/src/views/StoryHistoryPage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/StoryHistoryPage.vue).
- Affects frontend API bindings in [frontend/src/lib/api.js](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/lib/api.js).
