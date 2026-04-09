## Why

Recent user feedback shows the current interactive reading flow still feels visually loose, overly large, and sometimes unreliable under slow or unstable generation conditions. The current UI language is readable, but pacing and feedback are not yet robust enough for real usage: option cards consume too much viewport height, long-running generation can block users in waiting overlays, failure states are not explicit enough, header translucency harms readability, auto-scroll is inconsistent across repeated choices, situation notes feel awkward when they accumulate in history, and story beats feel too short at runtime.

This change aims to convert that feedback into a cohesive UX polish pass with spec-level acceptance criteria before implementation.

## What Changes

- Tighten visual density across bookshelf and active story pages, with emphasis on option card height, spacing rhythm, and oversized template cards.
- Replace blocking generation behavior with non-blocking waiting affordances so users can continue browsing while long tasks run.
- Add actionable timeout/network failure feedback for custom generation and seed workflows.
- Improve top header readability by pairing translucency with stronger blur and contrast-safe backing.
- Make auto-scroll behavior deterministic whenever new node content, reveal progress, or choice dock availability changes.
- Adjust situation-note rendering so it remains context-aware instead of continuously piling through the full scroll history.
- Extend perceived and actual narrative pacing by increasing node prose depth requirements.

## Capabilities

### Modified Capabilities

- `bookshelf-dashboard-experience`
- `interactive-story-reading-experience`
- `custom-doubao-story-generation`

## Impact

- Affects frontend views: [frontend/src/views/BookshelfPage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/BookshelfPage.vue), [frontend/src/views/StoryResultPage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/StoryResultPage.vue), and shared loading/presentation primitives such as [frontend/src/components/LoadingOverlay.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/components/LoadingOverlay.vue) and [frontend/src/styles.css](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/styles.css).
- May affect frontend request handling in [frontend/src/lib/api.js](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/lib/api.js) for timeout and error messaging flow.
- Affects story prose prompt constraints in [backend/app/story_prompts.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/story_prompts.py) to support longer, less abrupt storytelling.
